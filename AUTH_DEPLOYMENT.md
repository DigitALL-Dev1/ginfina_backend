# MFA on the deployed server

All account roles must complete email verification. `/api/auth/login` returns a temporary session only after the mail provider accepts the email. `/api/auth/verify-mfa` returns the access token and role after verification.

Configure these variables in the backend hosting service:

## Railway Free / Trial / Hobby: use HTTPS email

[Railway blocks SMTP on Free, Trial and Hobby plans](https://docs.railway.com/networking/outbound-networking). Changing SMTP ports will not enable email on those plans. The app now supports [Resend's HTTPS API](https://resend.com/docs/api-reference/emails/send-email).

Set these **backend** Railway variables, then redeploy:

```dotenv
EMAIL_PROVIDER=resend
RESEND_API_KEY=<your Resend API key>
EMAIL_FROM=GINFINA <login@your-verified-domain.example>
```

Replace the sender with an address on your verified Resend domain. Do not place the key in frontend variables or share it in chat. No SMTP credentials are needed for this provider. Check Resend delivery records and the recipient's spam folder if the provider accepted the message but it did not reach the inbox.

## SMTP on a host that permits it

Set `EMAIL_PROVIDER=smtp` and configure:

| Variable | Purpose |
| --- | --- |
| `SMTP_HOST` | Mail provider's SMTP hostname |
| `SMTP_PORT` | `587` for STARTTLS, or `465` for implicit TLS |
| `SMTP_USERNAME` | SMTP login |
| `SMTP_PASSWORD` | SMTP password or provider app password |
| `SMTP_FROM` | Sender address authorized by the provider |
| `SMTP_TIMEOUT_SECONDS` | Socket timeout; defaults to `15` |
| `SECRET_KEY` | A strong, stable signing secret shared by all backend instances |

Server environment variables take precedence over `.env` in authentication configuration. Redeploy after code or configuration changes. Request a fresh code if the signing secret changes; codes expire after five minutes. Provider acceptance does not guarantee inbox delivery, so also check spam and provider delivery records.

The frontend production build uses `https://ginfinabackend-production.up.railway.app/api`. If the frontend host defines `VITE_API_BASE_URL`, set it to that URL and rebuild; a host build variable overrides `.env.production`. Local development retains its local API setting.

## Diagnose failures

Authentication database reads have a five-second deadline and email delivery has an eighteen-second deadline. The frontend stops waiting for authentication requests after thirty seconds, displays a persistent error, and allows another attempt. It never retries email automatically. A mail provider might still finish a timed-out delivery; a late code belongs to that earlier attempt, so use the code from your current successful sign-in request.

- Login returns **503**, `auth.database.unavailable`: inspect MongoDB availability and backend database configuration.
- Login returns **503**, `auth.email.delivery_timeout`: inspect host outbound networking and email provider settings; use HTTPS email where SMTP is blocked.
- Login returns **503**, `auth.email.provider_rejected`: inspect the Resend API key, sender verification and provider delivery logs.

- Login returns **503**, `auth.email.not_configured`: required SMTP credentials are missing.
- Login returns **503**, `auth.email.failed: SMTPAuthenticationError`: check SMTP credentials and provider policy.
- Login returns **503**, `auth.email.failed: TimeoutError` or another connection error: check outbound SMTP connectivity, hostname and port on the backend host.
- Verification returns **401**, `auth.mfa.expired`: sign in again and use the new code.
- Verification returns **401**, `auth.mfa.invalid_session`: check that both requests use the same deployment and that all instances use the same `SECRET_KEY`.
- Verification returns **400**, `auth.mfa.incorrect_code`: use the code from the email for the current sign-in attempt.

Email failure logs include the error category and host/port, never verification codes, tokens, email bodies or passwords. Do not share those secrets when reporting an issue.

Run isolated checks (no live database or email traffic):

```powershell
python -B -m unittest discover -s tests -p test_auth_roles.py -v
```
