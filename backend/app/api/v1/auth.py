"""
NAADAMAYA auth routes (phone number + OTP).

    POST /auth/send-otp     sends a code to the phone number
    POST /auth/verify-otp   checks the code; creates the account or signs in
    POST /auth/refresh      exchanges a refresh token for a new pair (rotation)
    POST /auth/logout       ends this session (or every session)
    GET  /auth/me           the signed-in account

The routes only translate HTTP to service calls. All rules (limits, hashing,
one-account-per-number, token rotation) live in the services.

These are plain `def` routes: FastAPI runs them in a worker thread, which is
right for our synchronous database code.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import client_ip, get_current_user
from app.core.database import get_db
from app.core.exceptions import InvalidTokenError
from app.models.user import User
from app.schemas.auth import (
    AuthUser,
    LogoutRequest,
    RefreshRequest,
    RefreshResponse,
    SendOtpRequest,
    SendOtpResponse,
    VerifyOtpRequest,
    VerifyOtpResponse,
)
from app.schemas.common import COMMON_ERRORS, MessageResponse
from app.services.auth.auth_service import build_auth_user, send_login_otp, sign_in_with_otp
from app.services.auth.token_service import revoke_all_sessions, revoke_session, rotate_session

router = APIRouter(prefix="/auth", tags=["Auth"])


def _user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


@router.post(
    "/send-otp",
    response_model=SendOtpResponse,
    summary="Send a sign-in code",
    responses={422: COMMON_ERRORS[422], 429: COMMON_ERRORS[429]},
)
def send_otp(payload: SendOtpRequest, request: Request, db: Session = Depends(get_db)) -> SendOtpResponse:
    result = send_login_otp(
        db,
        payload.phone_number,
        ip=client_ip(request),
        device=_user_agent(request),
    )
    return SendOtpResponse(
        masked_phone=result.masked_phone,
        expires_in=result.expires_in,
        resend_after=result.resend_after,
        development_otp=result.development_otp,  # None unless OTP_MODE=development
    )


@router.post(
    "/verify-otp",
    response_model=VerifyOtpResponse,
    summary="Verify the code and sign in (creates the account on first use)",
    responses={422: COMMON_ERRORS[422], 429: COMMON_ERRORS[429]},
)
def verify_otp_route(payload: VerifyOtpRequest, request: Request, db: Session = Depends(get_db)) -> VerifyOtpResponse:
    result = sign_in_with_otp(
        db,
        payload.phone_number,
        payload.otp,
        ip=client_ip(request),
        user_agent=_user_agent(request),
        device_label=payload.device_label,
    )
    return VerifyOtpResponse(
        is_new_user=result.is_new_user,
        access_token=result.tokens.access_token,
        refresh_token=result.tokens.refresh_token,
        expires_in=result.tokens.expires_in,
        user=result.user,
    )


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    summary="Get a new access token (the refresh token is replaced)",
    responses={401: COMMON_ERRORS[401]},
)
def refresh(payload: RefreshRequest, request: Request, db: Session = Depends(get_db)) -> RefreshResponse:
    try:
        pair, _user = rotate_session(
            db,
            payload.refresh_token,
            ip=client_ip(request),
            user_agent=_user_agent(request),
        )
    except InvalidTokenError:
        # rotate_session may have committed a family revocation (token reuse).
        raise
    return RefreshResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        expires_in=pair.expires_in,
    )


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Sign out. Never fails, so the app can always clear its session.",
)
def logout(payload: LogoutRequest, db: Session = Depends(get_db)) -> MessageResponse:
    user_id = revoke_session(db, payload.refresh_token)
    if payload.all_devices and user_id is not None:
        revoke_all_sessions(db, user_id)
    return MessageResponse(message="Signed out.")


@router.get(
    "/me",
    response_model=AuthUser,
    summary="The signed-in account",
    responses={401: COMMON_ERRORS[401]},
)
def me(user: User = Depends(get_current_user)) -> AuthUser:
    return build_auth_user(user)
