from datetime import timedelta

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from prometheus_client import Counter
from sqlalchemy.orm import Session

from .. import bootstrap, crud, schemas, security
from ..audit_client import record_safely
from ..config import settings
from ..database import get_db
from ..deps import get_current_user, require_role
from ..models import Role, User

router = APIRouter(prefix="/auth", tags=["auth"])

LOGIN_FAILURES = Counter(
    "auth_login_failures_total", "Failed login attempts", ["reason"]
)


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
    # The bootstrap admin address is reserved: same generic error as any
    # taken address, so it can't be pre-registered as a viewer to block the
    # admin's creation (and doesn't reveal that it's special).
    is_bootstrap_email = str(user_in.email).strip().lower() == bootstrap.bootstrap_email()
    if crud.get_user_by_email(db, user_in.email) or is_bootstrap_email:
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
        # Every failure is counted (alertable: a spike is credential
        # stuffing), but only failures against a REAL account are written to
        # the audit trail. The trail is append-only and kept forever, so
        # auditing attempts against arbitrary attacker-chosen strings would
        # let anyone fill it with junk; for a real account the actor is
        # bounded and the record is genuinely useful. No password is ever
        # recorded.
        LOGIN_FAILURES.labels(reason="bad_password" if user else "unknown_user").inc()
        if user:
            record_safely(
                actor=user.email, action="user.login_failed", resource_type="user", resource_id=user.id,
            )
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


@router.patch("/users/{user_id}/role", response_model=schemas.UserOut)
def change_role(
    user_id: str,
    payload: schemas.RoleUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(Role.admin)),
):
    target = crud.get_user_by_id(db, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    if target.id == admin.id:
        # Prevents the last admin demoting themselves into a platform with
        # nobody able to grant roles; another admin can still change it.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="admins cannot change their own role"
        )

    before = target.role.value
    updated = crud.set_role(db, target, payload.role)
    record_safely(
        actor=admin.email, action="user.role_changed", resource_type="user", resource_id=updated.id,
        before_state={"role": before}, after_state={"role": updated.role.value},
    )
    return updated
