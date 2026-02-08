"""
Authentication Module
Handles JWT token creation and verification for API security.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, Union, Any
import hashlib
import hmac
try:
    from jose import JWTError, jwt
except ModuleNotFoundError:  # pragma: no cover - depends on environment packaging
    import jwt
    from jwt import PyJWTError as JWTError
try:
    from passlib.context import CryptContext
except ModuleNotFoundError:  # pragma: no cover - depends on environment packaging
    CryptContext = None
from pydantic import BaseModel
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import logging

from config import load_config, PerceptixConfig
from models import SystemMode

# Configure logging
logger = logging.getLogger("PerceptixAuth")

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto") if CryptContext else None
INSECURE_DEMO_JWT_SECRET = "insecure-change-me-for-production"

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Union[str, None] = None
    scopes: list[str] = []
    is_admin: bool = False

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    if pwd_context:
        return pwd_context.verify(plain_password, hashed_password)

    if hashed_password.startswith("sha256$"):
        expected = "sha256$" + hashlib.sha256(plain_password.encode("utf-8")).hexdigest()
        return hmac.compare_digest(expected, hashed_password)

    return hmac.compare_digest(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Hash a password."""
    if pwd_context:
        return pwd_context.hash(password)
    return "sha256$" + hashlib.sha256(password.encode("utf-8")).hexdigest()

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None, config: Optional[PerceptixConfig] = None) -> str:
    """
    Create a JWT access token.
    
    Args:
        data: Payload data
        expires_delta: Optional expiration time
        config: Configuration object (to get secret key)
    
    Returns:
        str: Encoded JWT token
    """
    if config is None:
        config = load_config()

    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
        
    to_encode.update({"exp": expire})
    
    # Use configured secret key, but allow a fallback only outside production mode.
    if config.api.jwt_secret_key:
        secret_key = config.api.jwt_secret_key
    elif config.system.mode == SystemMode.PRODUCTION:
        raise RuntimeError("JWT_SECRET_KEY must be set when PERCEPTIX_MODE=PRODUCTION")
    else:
        secret_key = INSECURE_DEMO_JWT_SECRET
    algorithm = config.api.jwt_algorithm
    
    encoded_jwt = jwt.encode(to_encode, secret_key, algorithm=algorithm)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)) -> TokenData:
    """
    Validate and return the current user from the token.
    
    Args:
        token: JWT token
        
    Returns:
        TokenData: User data extracted from token
        
    Raises:
        HTTPException: If token is invalid
    """
    config = load_config()
    if config.api.jwt_secret_key:
        secret_key = config.api.jwt_secret_key
    elif config.system.mode == SystemMode.PRODUCTION:
        logger.error("JWT_SECRET_KEY is required when PERCEPTIX_MODE=PRODUCTION")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server authentication is not configured"
        )
    else:
        secret_key = INSECURE_DEMO_JWT_SECRET
    algorithm = config.api.jwt_algorithm
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(
            username=username,
            is_admin=bool(payload.get("adm", False)),
        )
    except JWTError:
        raise credentials_exception
        
    return token_data
