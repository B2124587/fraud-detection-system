"""Authentication service — JWT (PyJWT) + stdlib PBKDF2 password hashing.

Uses only the Python standard library for password hashing (hashlib.pbkdf2_hmac)
and PyJWT for tokens. Both install as pure-Python/pre-built wheels with no
compiler or extra system dependencies required — convenient on Windows.
"""
from datetime import datetime, timedelta
from typing import Optional

import hashlib
import hmac
import secrets

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.config import settings
from app.models.database import get_db
from app.models.orm_models import UserProfile, UserRole

bearer_scheme = HTTPBearer()

PBKDF2_ITERATIONS = 260_000

RBAC_PERMISSIONS = {
    UserRole.SYSTEM_ADMIN: {
        "manage_users", "view_dashboard", "review_alerts", "override_fraud",
        "flag_transaction", "manage_blocklist", "retrain_models",
        "view_audit_log", "export_compliance", "report_signals",
        "manage_reference_data", "view_analytics",
    },
    UserRole.FRAUD_ANALYST: {
        "view_dashboard", "review_alerts", "override_fraud",
        "flag_transaction", "view_audit_log", "report_signals",
        "view_analytics", "export_compliance",
    },
    UserRole.MOBILE_USER: set(),
    UserRole.OPERATOR_API: {"score_transaction", "flag_transaction", "view_health"},
}


def hash_password(password: str) -> str:
    """Hash a password with PBKDF2-HMAC-SHA256, stdlib only.

    Stored as "pbkdf2_sha256$iterations$salt_hex$hash_hex".
    """
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(plain: str, hashed: str) -> bool:
    try:
        scheme, iterations, salt, digest_hex = hashed.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        check = hashlib.pbkdf2_hmac(
            "sha256", plain.encode("utf-8"), bytes.fromhex(salt), int(iterations)
        )
        return hmac.compare_digest(check.hex(), digest_hex)
    except (ValueError, AttributeError):
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> UserProfile:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(credentials.credentials)
        user_id: int = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception

    user = db.query(UserProfile).filter(
        UserProfile.id == int(user_id),
        UserProfile.is_portal_user == True,
        UserProfile.is_active == True,
    ).first()

    if user is None:
        raise credentials_exception

    user.last_login = datetime.utcnow()
    db.commit()
    return user


def require_permission(permission: str):
    """Dependency factory: raises 403 if user lacks the required permission."""
    async def _check(current_user: UserProfile = Depends(get_current_user)):
        allowed = RBAC_PERMISSIONS.get(current_user.role, set())
        if permission not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission}' required. Your role: {current_user.role}",
            )
        return current_user
    return _check


def authenticate_user(db: Session, username: str, password: str) -> Optional[UserProfile]:
    user = db.query(UserProfile).filter(
        UserProfile.username == username,
        UserProfile.is_portal_user == True,
        UserProfile.is_active == True,
    ).first()
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user
