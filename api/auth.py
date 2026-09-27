from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime, timedelta
import bcrypt
import jwt
from motor.motor_asyncio import AsyncIOMotorClient
import uuid
import os
import secrets
import logging
import smtplib
import ssl
import asyncio
import requests
from pymongo.errors import PyMongoError
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv(override=False)
logger = logging.getLogger(__name__)

# MongoDB Configuration
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "ginfina")
client = AsyncIOMotorClient(MONGODB_URL, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000, socketTimeoutMS=5000)
db = client[DATABASE_NAME]
users_collection = db["users"]

# SMTP Configuration
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USERNAME or "noreply@gx1.com")
SMTP_TIMEOUT_SECONDS = float(os.getenv("SMTP_TIMEOUT_SECONDS", "15"))
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "resend" if RESEND_API_KEY else "smtp").strip().lower()
EMAIL_FROM = os.getenv("EMAIL_FROM", "").strip()
EMAIL_DELIVERY_DEADLINE_SECONDS = 18
AUTH_DATABASE_DEADLINE_SECONDS = 5


def send_resend_email(to_email: str, subject: str, body: str):
    """HTTPS transport for hosts where outbound SMTP is unavailable."""
    if not RESEND_API_KEY or not EMAIL_FROM:
        logger.error("auth.email.not_configured: Resend requires RESEND_API_KEY and EMAIL_FROM")
        raise HTTPException(status_code=503, detail="Email delivery is not configured on the server. Contact your administrator.")
    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            json={"from": EMAIL_FROM, "to": [to_email], "subject": subject, "html": body},
            timeout=(5, 10),
        )
        if not response.ok:
            logger.error("auth.email.provider_rejected: provider=resend status=%s", response.status_code)
            raise HTTPException(status_code=503, detail="The email provider rejected delivery. Contact your administrator to check the email configuration.")
        if not response.json().get("id"):
            raise ValueError("Missing provider message identifier")
        logger.info("auth.email.accepted: provider=resend")
        return True
    except (requests.RequestException, ValueError) as exc:
        logger.error("auth.email.failed: provider=resend category=%s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Unable to send the verification email. Please try again.") from exc


async def run_email_delivery(function, *args):
    # A socket timeout alone does not bound DNS lookup or multiple SMTP commands.
    try:
        return await asyncio.wait_for(run_in_threadpool(function, *args), timeout=EMAIL_DELIVERY_DEADLINE_SECONDS)
    except asyncio.TimeoutError as exc:
        logger.error("auth.email.delivery_timeout: provider=%s", EMAIL_PROVIDER)
        raise HTTPException(status_code=503, detail="Email delivery timed out. Please try again or contact your administrator.") from exc

def send_email(to_email: str, subject: str, body: str):
    if EMAIL_PROVIDER == "resend":
        return send_resend_email(to_email, subject, body)
    if EMAIL_PROVIDER != "smtp":
        logger.error("auth.email.not_configured: unsupported EMAIL_PROVIDER")
        raise HTTPException(status_code=503, detail="Email delivery is not configured correctly. Contact your administrator.")
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        logger.error("auth.email.not_configured: SMTP_USERNAME or SMTP_PASSWORD is missing")
        raise HTTPException(status_code=503, detail="Email delivery is not configured on the server. Contact your administrator.")
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_FROM
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html' if "<html>" in body else 'plain'))
        
        context = ssl.create_default_context()
        connection = (smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS, context=context)
                      if SMTP_PORT == 465 else smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS))
        with connection as server:
            if SMTP_PORT != 465:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
        logger.info("auth.email.accepted: SMTP provider accepted the message")
        return True
    except (OSError, smtplib.SMTPException) as exc:
        # Record the failure category, never the message body, code or credentials.
        logger.error("auth.email.failed: %s (host=%s port=%s)", type(exc).__name__, SMTP_HOST, SMTP_PORT)
        raise HTTPException(status_code=503, detail="Unable to send the email. Please try again or contact your administrator.") from exc

async def init_db():
    """Initialize MongoDB collections and create indexes"""
    # Create unique index on email field
    await users_collection.create_index("email", unique=True)
    
    # Seed mock users if collection is empty
    count = await users_collection.count_documents({})
    if count == 0:
        def hash_password(password: str) -> str:
            salt = bcrypt.gensalt()
            hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
            return hashed.decode('utf-8')
            
        mock_users = [
            {
                "_id": "user-1",
                "name": "Admin User",
                "email": "admin@gx1.com",
                "password_hash": hash_password("admin123"),
                "role": "admin",
                "subscription_plan": "premium",
                "is_active": True,
                "created_at": datetime.utcnow()
            },
            {
                "_id": "user-2",
                "name": "External Consultant",
                "email": "consultant@gx1.com",
                "password_hash": hash_password("consultant123"),
                "role": "consultant",
                "subscription_plan": "free",
                "is_active": True,
                "created_at": datetime.utcnow()
            },
            {
                "_id": "user-3",
                "name": "Standard User",
                "email": "user@gx1.com",
                "password_hash": hash_password("user123"),
                "role": "user",
                "subscription_plan": "free",
                "is_active": True,
                "created_at": datetime.utcnow()
            },
            {
                "_id": "user-4",
                "name": "Zain Israr",
                "email": "zain.israr@greendigitall.com",
                "password_hash": hash_password("zain123"),
                "role": "admin",
                "subscription_plan": "premium",
                "is_active": True,
                "created_at": datetime.utcnow()
            }
        ]
        await users_collection.insert_many(mock_users)
        print("Mock users seeded successfully")

# JWT Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "testing-key-gx1")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
MFA_TEMP_TOKEN_EXPIRE_MINUTES = 5

# Pydantic Models
class UserLogin(BaseModel):
    email: str  # Accepts email or username
    password: str

class VerifyMfaRequest(BaseModel):
    code: str
    temp_token: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

class GoogleLoginRequest(BaseModel):
    credential: str

class Token(BaseModel):
    access_token: str
    token_type: str
    name: str
    user_id: str
    role: str

class User(BaseModel):
    id: str
    name: str
    email: str
    role: str
    subscription_plan: str
    is_active: bool
    created_at: datetime

# Router and Security
router = APIRouter()
security = HTTPBearer()

# Utility Functions
def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_temp_token(email: str, code: str):
    expire = datetime.utcnow() + timedelta(minutes=MFA_TEMP_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": email, "code": code, "type": "mfa_temp", "exp": expire}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str) -> str:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None or payload.get("type") not in (None, "access"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials"
            )
        return email
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )

async def get_user_by_email_or_username(identifier: str):
    """Get user from MongoDB by email or username"""
    try:
        user = await asyncio.wait_for(users_collection.find_one({
            "$or": [
                {"email": identifier},
                {"name": identifier}
            ]
        }), timeout=AUTH_DATABASE_DEADLINE_SECONDS)
    except (asyncio.TimeoutError, PyMongoError) as exc:
        logger.error("auth.database.unavailable: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Sign-in service is temporarily unavailable. Please try again.") from exc
    return user

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    email = verify_token(credentials.credentials)
    user = await get_user_by_email_or_username(email)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    return user

def start_mfa_challenge(user: dict):
    """Require email verification for every role before issuing an access token."""
    # Generate random 6-digit code
    code = f"{secrets.randbelow(1000000):06d}"
    
    # Send MFA code email
    subject = "Your GINFINIA Sign-In Verification Code"
    body = f"""
    <html>
        <body>
            <h2>GINFINIA Access Verification</h2>
            <p>Hello {user['name']},</p>
            <p>A sign-in attempt was detected requiring Multi-Factor Authentication.</p>
            <p>Your 6-digit verification code is: <strong>{code}</strong></p>
            <p>This code is valid for 5 minutes.</p>
            <br>
            <p>Secure. Governed. Integrated.</p>
        </body>
    </html>
    """
    if not send_email(user["email"], subject, body):
        raise HTTPException(status_code=503, detail="Unable to send the verification email. Please try again.")
    
    temp_token = create_temp_token(user["email"], code)
    return {
        "mfa_required": True,
        "temp_token": temp_token,
        "message": "MFA verification required. A 6-digit code has been sent to your email."
    }

# Authentication Endpoints

@router.post("/login")
async def login(user_data: UserLogin):
    user = await get_user_by_email_or_username(user_data.email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email/username or password"
        )
    
    if not verify_password(user_data.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email/username or password"
        )
    
    return await run_email_delivery(start_mfa_challenge, user)

@router.post("/verify-mfa", response_model=Token)
async def verify_mfa(mfa_data: VerifyMfaRequest):
    try:
        payload = jwt.decode(mfa_data.temp_token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "mfa_temp" or not payload.get("sub") or not payload.get("code"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid MFA session token"
            )
        email = payload.get("sub")
        correct_code = payload.get("code")
    except jwt.ExpiredSignatureError:
        logger.info("auth.mfa.expired")
        raise HTTPException(status_code=401, detail="Verification session expired. Sign in again to request a new code.")
    except jwt.PyJWTError as exc:
        logger.warning("auth.mfa.invalid_session: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid verification session. Sign in again and use the newest email code."
        )
    
    # Verify the code
    supplied_code = mfa_data.code.strip()
    if len(supplied_code) != 6 or not supplied_code.isascii() or not supplied_code.isdigit() or not secrets.compare_digest(supplied_code, str(correct_code)):
        logger.info("auth.mfa.incorrect_code")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect verification code. Please check and try again."
        )
    
    user = await get_user_by_email_or_username(email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["email"]}, 
        expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "name": user["name"],
        "user_id": str(user["_id"]),
        "role": str(user.get("role", "")).strip().upper()
    }

@router.post("/forgot-password")
async def forgot_password(reset_data: ForgotPasswordRequest):
    user = await get_user_by_email_or_username(reset_data.email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email address not registered in system"
        )
    
    # Generate password reset JWT token valid for 15 minutes
    expire = datetime.utcnow() + timedelta(minutes=15)
    reset_token = jwt.encode(
        {"sub": user["email"], "type": "password_reset", "exp": expire},
        SECRET_KEY,
        algorithm=ALGORITHM
    )
    
    # Construct link
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:4174")
    reset_link = f"{FRONTEND_URL}/reset-password?token={reset_token}"
    
    # Send email
    subject = "Reset Your GINFINIA Password"
    body = f"""
    <html>
        <body>
            <h2>GINFINIA Password Reset</h2>
            <p>Hello {user['name']},</p>
            <p>We received a request to reset your password. Click the link below to complete the request:</p>
            <p><a href="{reset_link}">Reset Password</a></p>
            <p>If you did not request this, you can ignore this email.</p>
        </body>
    </html>
    """
    await run_email_delivery(send_email, user["email"], subject, body)
    
    return {
        "message": f"A password reset link has been successfully generated and sent to {reset_data.email}."
    }

@router.post("/reset-password")
async def reset_password(reset_data: ResetPasswordRequest):
    try:
        payload = jwt.decode(reset_data.token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "password_reset":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid password reset token"
            )
        email = payload.get("sub")
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password reset link is invalid or expired"
        )
    
    user = await get_user_by_email_or_username(email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    new_hash = hash_password(reset_data.new_password)
    
    # Update MongoDB database
    await users_collection.update_one(
        {"email": email},
        {"$set": {"password_hash": new_hash}}
    )
    
    return {"message": "Your password has been successfully updated."}

@router.post("/google-login")
async def google_login(google_data: GoogleLoginRequest):
    email = "google_user@gx1.com"
    user = await get_user_by_email_or_username(email)
    
    if not user:
        user_id = str(uuid.uuid4())
        new_user = {
            "_id": user_id,
            "name": "Google User",
            "email": email,
            "password_hash": "",
            "role": "user",
            "subscription_plan": "free",
            "is_active": True,
            "created_at": datetime.utcnow()
        }
        await users_collection.insert_one(new_user)
        user = await get_user_by_email_or_username(email)
        
    return await run_email_delivery(start_mfa_challenge, user)

@router.get("/me", response_model=User)
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    return User(
        id=str(current_user["_id"]),
        name=current_user["name"],
        email=current_user["email"],
        role=current_user["role"],
        subscription_plan=current_user["subscription_plan"],
        is_active=current_user["is_active"],
        created_at=current_user["created_at"]
    )
