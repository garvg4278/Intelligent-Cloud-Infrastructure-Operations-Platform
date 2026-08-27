import jwt as pyjwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from . import crud
from .config import settings
from .database import get_db
from .models import Role, User
from .security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token, settings.SECRET_KEY)
    except pyjwt.PyJWTError:
        raise credentials_exception from None

    if payload.get("type") != "access":
        raise credentials_exception

    email = payload.get("sub")
    if not email:
        raise credentials_exception

    user = crud.get_user_by_email(db, email)
    if user is None or not user.is_active:
        raise credentials_exception
    return user


def require_role(*allowed_roles: Role):
    def role_checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return user

    return role_checker
