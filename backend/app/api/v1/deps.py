"""
NAADAMAYA API dependencies.

    user: User = Depends(get_current_user)       # any signed-in, active user
    admin: User = Depends(require_admin)         # ADMIN role only
    ip = client_ip(request)

get_current_user:
  1. reads "Authorization: Bearer <access token>"
  2. validates signature, expiry and type (core/security.py)
  3. loads the user FROM THE DATABASE and checks the account is still
     ACTIVE and not deleted. A suspended or deleted user is stopped here even
     if their 15-minute access token is still valid.
  4. puts the user id in the logging context and updates last_seen_at
     (at most once every few minutes, to avoid a write on every request)

The user id always comes from the verified token, never from anything the
client sends in a body, query or header.
"""

import uuid
from datetime import timedelta

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import AuthRequiredError, ForbiddenError, InvalidTokenError
from app.core.logging import user_id_var
from app.core.security import decode_access_token, utcnow
from app.models.enums import UserRole
from app.models.user import User
from app.services.auth.auth_service import require_user

# auto_error=False so a missing header gives OUR error shape, not FastAPI's.
bearer_scheme = HTTPBearer(auto_error=False, description="Access token from /auth/verify-otp")

LAST_SEEN_INTERVAL = timedelta(minutes=5)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise AuthRequiredError()

    payload = decode_access_token(credentials.credentials)
    try:
        user_id = uuid.UUID(str(payload["sub"]))
    except (ValueError, KeyError) as exc:
        raise InvalidTokenError() from exc

    user = require_user(db, user_id)   # raises if missing, suspended or deleted

    now = utcnow()
    if user.last_seen_at is None or now - user.last_seen_at > LAST_SEEN_INTERVAL:
        user.last_seen_at = now

    user_id_var.set(str(user.id))
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.ADMIN.value:
        # Answer like a missing page so normal users cannot discover admin routes.
        raise ForbiddenError("You do not have permission to do this.")
    return user


def client_ip(request: Request) -> str | None:
    """Connection address. Behind a proxy, configure the proxy headers at the server level."""
    return request.client.host if request.client else None
