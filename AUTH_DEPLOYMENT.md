# SMTP MFA on your VPS

All account roles must complete email verification. `/api/auth/login` sends the code through SMTP to the signing-in user's stored email address. It returns a temporary session only after the SMTP server accepts the message. `/api/auth/verify-mfa` returns the access token and role after verification.

## Backend configuration

Configure the following in the VPS backend environment or its private `.env` file:

```dotenv
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-sending-account@gmail.com
SMTP_PASSWORD=your-smtp-app-password
SMTP_FROM=your-sending-account@gmail.com
SMTP_TIMEOUT_SECONDS=15
FRONTEND_URL=https://your-frontend-domain.example
SECRET_KEY=replace-with-a-strong-stable-signing-secret
```

Replace all example values with your actual settings. For another email provider, use its SMTP hostname, credentials and authorized sender address. The implementation uses STARTTLS on port `587` and implicit TLS on port `465`. The VPS must permit outbound connections to the configured SMTP host and port. The sender is configured by `SMTP_FROM`; recipients come from user records, not from a fixed test recipient.

SMTP is the only email transport; no provider-selection variable or email API key is required. Authentication reads server environment variables before local `.env` values. Keep the existing MongoDB configuration and restart the backend after changes. Keep `.env` out of Git.

Set `FRONTEND_URL` to the deployed frontend origin so password reset links point to the right website. Keep the same `SECRET_KEY` across backend instances. Changing it invalidates existing sessions, including pending MFA attempts. Codes expire after five minutes.

## Frontend configuration

Before building the frontend for the VPS, set:

```dotenv
VITE_API_BASE_URL=https://your-backend-domain.example/api
VITE_DEMO_MODE=false
```

Use the actual public backend address. The repository's production frontend configuration currently points to the previous Railway backend; override it with your VPS address and rebuild before deployment. Never place SMTP credentials in frontend variables. Local development can continue using `http://127.0.0.1:8001/api`.

## Diagnose failures

Authentication database reads have a five-second deadline and email delivery has an eighteen-second deadline. The frontend stops waiting for authentication requests after thirty seconds, displays a persistent error, and allows another attempt. It never retries email automatically. A mail server might still finish a timed-out delivery; use the code from your current successful sign-in request.

- **503**, `auth.database.unavailable`: check MongoDB availability and backend database configuration.
- **503**, `auth.email.delivery_timeout`: check VPS outbound connectivity and SMTP settings.
- **503**, `auth.email.not_configured`: SMTP credentials are missing.
- **503**, `auth.email.failed: SMTPAuthenticationError`: check credentials and your mail provider's authentication requirements.
- **503**, `auth.email.failed: TimeoutError` or another connection error: check hostname, port, firewall and hosting-provider SMTP restrictions.
- **401**, `auth.mfa.expired`: sign in again and use the new code.
- **401**, `auth.mfa.invalid_session`: check that requests use the same deployment and all instances use the same signing secret.
- **400**, `auth.mfa.incorrect_code`: use the code from the email for the current sign-in attempt.

SMTP acceptance does not guarantee inbox delivery. Check the recipient address, spam folder and mail-provider delivery records. Logs exclude verification codes, tokens, email bodies and passwords.

Run isolated checks from the backend directory (no live database or email traffic):

```powershell
python -B -m unittest discover -s tests -p test_auth_roles.py -v
```
