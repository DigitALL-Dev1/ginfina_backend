from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime, timedelta
import bcrypt
import jwt
from motor.motor_asyncio import AsyncIOMotorClient
import uuid
import os
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv(override=True)

# MongoDB Configuration
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "ginfina")
client = AsyncIOMotorClient(MONGODB_URL)
db = client[DATABASE_NAME]
users_collection = db["users"]

# SMTP Configuration
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USERNAME or "noreply@gx1.com")

def send_email(to_email: str, subject: str, body: str):
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        print("\n" + "="*50)
        print(f"[MOCK EMAIL - CONFIGURE SMTP IN .env TO SEND REAL EMAILS]")
        print(f"To: {to_email}")
        print(f"Subject: {subject}")
        print(f"Body: {body}")
        print("="*50 + "\n")
        return False
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_FROM
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html' if "<html>" in body else 'plain'))
        
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
        print(f"Successfully sent email to {to_email}")
        return True
    except Exception as e:
        print(f"Failed to send email to {to_email}: {e}")
        return False

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
        if email is None:
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
    user = await users_collection.find_one({
        "$or": [
            {"email": identifier},
            {"name": identifier}
        ]
    })
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
    
    # Check if role requires MFA: Admin or External Consultant
    if user["role"] in ["admin", "consultant"]:
        # Generate random 6-digit code
        code = f"{random.randint(100000, 999999)}"
        
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
        send_email(user["email"], subject, body)
        
        temp_token = create_temp_token(user["email"], code)
        return {
            "mfa_required": True,
            "temp_token": temp_token,
            "message": "MFA verification required. A 6-digit code has been sent to your email."
        }
    
    # Standard user login
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["email"]}, 
        expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "name": user["name"],
        "user_id": str(user["_id"])
    }

@router.post("/verify-mfa", response_model=Token)
async def verify_mfa(mfa_data: VerifyMfaRequest):
    try:
        payload = jwt.decode(mfa_data.temp_token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "mfa_temp":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid MFA session token"
            )
        email = payload.get("sub")
        correct_code = payload.get("code")
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="MFA session expired or invalid"
        )
    
    # Verify the code
    if mfa_data.code != correct_code:
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
        "user_id": str(user["_id"])
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
    send_email(user["email"], subject, body)
    
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

@router.post("/google-login", response_model=Token)
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
        
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["email"]}, 
        expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "name": user["name"],
        "user_id": str(user["_id"])
    }

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