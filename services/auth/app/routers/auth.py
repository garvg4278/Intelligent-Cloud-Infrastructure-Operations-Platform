from datetime import timedelta

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from .. import crud, schemas, security
from ..audit_client import record_safely
from ..config import settings
from ..database import get_db
from ..deps import get_current_user, require_role
from ..models import Role, User

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue_tokens(user: User) -> schemas.Token:
    access = security.create_token(
        user.email, user.role.value, "access",
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES), settings.SECRET_KEY,
    )
    refresh_tok = security.create_token(
        user.email, user.role.value, "refresh",
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS), settings.SECRET_KEY,
    )
    return schemas.Token(access_token=access, refresh_token=refresh_tok)


@router.post("/register", response_model=schemas.UserOut, status_code=status.HTTP_201_CREATED)
def register(user_in: schemas.UserCreate, db: Session = Depends(get_db)):
    if crud.get_user_by_email(db, user_in.email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    # Public registration always lands as "viewer" -- anything more
    # privileged has to be granted by an existing admin via a future
    # admin-only endpoint, not self-assigned at signup.
    user = crud.create_user(db, user_in, role=Role.viewer)
    record_safely(
        actor=user.email, action="user.registered", resource_type="user", resource_id=user.id,
        after_state={"email": user.email, "role": user.role.value},
    )
    return user


@router.post("/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = crud.get_user_by_email(db, form_data.username)
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is disabled")
    record_safely(actor=user.email, action="user.login", resource_type="user", resource_id=user.id)
    return _issue_tokens(user)


@router.post("/refresh", response_model=schemas.Token)
def refresh(payload: schemas.RefreshRequest, db: Session = Depends(get_db)):
    try:
        decoded = security.decode_token(payload.refresh_token, settings.SECRET_KEY)
    except pyjwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        ) from None

    if decoded.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    user = crud.get_user_by_email(db, decoded.get("sub", ""))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive or not found")

    return _issue_tokens(user)


@router.get("/me", response_model=schemas.UserOut)
def read_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("/users", response_model=list[schemas.UserOut])
def list_users(db: Session = Depends(get_db), _admin: User = Depends(require_role(Role.admin))):
    return crud.list_users(db)
