# Accounts API

Base path: `/api/v1/auth/`. Requests and responses use JSON. State-changing endpoints accept `POST`; `me/` accepts `GET`. Errors return `{"error": "..."}`. Responses use `Cache-Control: no-store`.

| Endpoint | Request fields | Success |
| --- | --- | --- |
| `register/` | `email`, `password` | `201` with user ID, email, pending status; verification email sent |
| `verify-email/` | `token` | `200` with active status |
| `resend-verification/` | `email` | `200` with generic response |
| `login/` | `email`, `password` | `200` with access and refresh tokens |
| `refresh/` | `refresh_token` | `200` with a new access and refresh token pair |
| `logout/` | `refresh_token` | `200`; revokes the refresh session |
| `password-reset/request/` | `email` | `200` with generic response |
| `password-reset/confirm/` | `token`, `password` | `200`; changes password and revokes refresh sessions |
| `me/` | `Authorization: Bearer <access_token>` | `200` with ID, email, status, roles |

Passwords must pass Django's configured validators, including a minimum of 12 characters. Email addresses are trimmed and lowercased. Registration creates a pending account with the student role. Verification tokens are valid for 24 hours; reset tokens for 1 hour. Issuing a new action token invalidates earlier unused tokens of the same purpose.

Access tokens are signed HS256 JWTs valid for 15 minutes. Refresh tokens are opaque random values valid for 30 days; only SHA-256 hashes are stored. Each refresh rotates its token, so the prior value cannot be reused. Logout and password reset revoke refresh sessions. Already issued access tokens remain valid until their short expiry unless the account is suspended. Future API apps can use `accounts.authentication.authenticated_user(request)` for bearer authentication.

The default debug email backend prints verification and reset tokens to the server console when `AUTH_FRONTEND_URL` is empty. Set `AUTH_FRONTEND_URL` to generate browser links instead. Production requires an SMTP backend and a long random `JWT_SIGNING_KEY`.
