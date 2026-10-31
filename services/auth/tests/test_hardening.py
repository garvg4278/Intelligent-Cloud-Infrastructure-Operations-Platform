"""Phase 8 hardening tests for the auth service.

Each reproduces a defect found by the pre-hardening review: a 500 on long
multi-byte passwords, no way to ever create an admin, no way to change a
role, case-variant duplicate accounts, and unaudited failed logins.
"""

import pytest

from app import bootstrap, crud, models, schemas
from app.config import Settings, settings


def _register(client, email, password="supersecret1"):
    return client.post("/auth/register", json={"email": email, "password": password})


def _login(client, email, password="supersecret1"):
    return client.post("/auth/login", data={"username": email, "password": password})


def _admin_headers(client, db_session, email="root@example.com"):
    crud.create_user(
        db_session, schemas.UserCreate(email=email, password="supersecret1"), role=models.Role.admin
    )
    token = _login(client, email).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ---- bcrypt byte limit -----------------------------------------------------

def test_multibyte_password_over_72_bytes_is_a_clean_422_not_a_500(client):
    # 40 characters, 80 bytes: passed the old character-count check.
    resp = _register(client, "uni@example.com", password="é" * 40)
    assert resp.status_code == 422
    assert "72 bytes" in resp.text


def test_multibyte_password_within_72_bytes_still_works(client):
    assert _register(client, "ok@example.com", password="é" * 30).status_code == 201  # 60 bytes
    assert _login(client, "ok@example.com", password="é" * 30).status_code == 200


def test_login_with_overlong_password_is_401_not_500(client):
    _register(client, "long@example.com")
    resp = _login(client, "long@example.com", password="x" * 200)
    assert resp.status_code == 401


# ---- email case-insensitivity ------------------------------------------------

def test_case_variant_of_existing_email_cannot_register_a_second_account(client):
    assert _register(client, "Alice@Example.com").status_code == 201
    assert _register(client, "alice@example.com").status_code == 400
    assert _register(client, "ALICE@EXAMPLE.COM").status_code == 400


def test_login_is_case_insensitive_and_email_is_stored_lowercase(client):
    body = _register(client, "Bob@Example.com").json()
    assert body["email"] == "bob@example.com"
    assert _login(client, "BOB@example.COM").status_code == 200


# ---- failed logins: audited for real accounts, counted for all ----------------------------------

def test_failed_login_is_audited_without_the_password(client, audit_client):
    _register(client, "carol@example.com")
    _login(client, "carol@example.com", password="definitely-wrong")
    failed = [c for c in audit_client.calls if c["action"] == "user.login_failed"]
    assert len(failed) == 1
    assert failed[0]["actor"] == "carol@example.com"
    assert "definitely-wrong" not in str(failed[0])


def test_failed_login_for_unknown_user_is_counted_but_not_audited(client, audit_client):
    from app.routers.auth import LOGIN_FAILURES

    before = LOGIN_FAILURES.labels(reason="unknown_user")._value.get()
    _login(client, "nobody@example.com")
    assert not any(c["action"] == "user.login_failed" for c in audit_client.calls)
    assert LOGIN_FAILURES.labels(reason="unknown_user")._value.get() == before + 1


# ---- role change -----------------------------------------------------------------

def test_admin_can_change_a_users_role_and_it_is_audited_with_the_admins_identity(
    client, db_session, audit_client
):
    target = _register(client, "dev@example.com").json()
    headers = _admin_headers(client, db_session)

    resp = client.patch(f"/auth/users/{target['id']}/role", json={"role": "operator"}, headers=headers)

    assert resp.status_code == 200
    assert resp.json()["role"] == "operator"
    event = next(c for c in audit_client.calls if c["action"] == "user.role_changed")
    assert event["actor"] == "root@example.com"  # the admin, not "system"
    assert event["before_state"] == {"role": "viewer"}
    assert event["after_state"] == {"role": "operator"}


def test_non_admin_cannot_change_roles_including_their_own(client):
    me = _register(client, "sneaky@example.com").json()
    token = _login(client, "sneaky@example.com").json()["access_token"]
    resp = client.patch(
        f"/auth/users/{me['id']}/role", json={"role": "admin"}, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 403


def test_admin_cannot_change_their_own_role(client, db_session):
    headers = _admin_headers(client, db_session)
    me = client.get("/auth/me", headers=headers).json()
    resp = client.patch(f"/auth/users/{me['id']}/role", json={"role": "viewer"}, headers=headers)
    assert resp.status_code == 400


def test_role_change_rejects_unknown_role_and_unknown_user(client, db_session):
    headers = _admin_headers(client, db_session)
    target = _register(client, "x@example.com").json()
    bad_role = client.patch(f"/auth/users/{target['id']}/role", json={"role": "root"}, headers=headers)
    assert bad_role.status_code == 422
    assert client.patch("/auth/users/nope/role", json={"role": "viewer"}, headers=headers).status_code == 404


# ---- bootstrap admin ----------------------------------------------------------------

@pytest.fixture()
def bootstrap_settings(monkeypatch):
    monkeypatch.setattr(settings, "BOOTSTRAP_ADMIN_EMAIL", "Boss@Example.com")
    monkeypatch.setattr(settings, "BOOTSTRAP_ADMIN_PASSWORD", "a-strong-passphrase")


def test_bootstrap_is_a_noop_when_unconfigured(db_session):
    assert bootstrap.ensure_bootstrap_admin(db_session) == "disabled"
    assert crud.list_users(db_session) == []


def test_bootstrap_creates_a_working_admin_exactly_once(client, db_session, bootstrap_settings):
    assert bootstrap.ensure_bootstrap_admin(db_session) == "created"
    assert bootstrap.ensure_bootstrap_admin(db_session) == "exists"
    assert len(crud.list_users(db_session)) == 1

    token = _login(client, "boss@example.com", password="a-strong-passphrase").json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["role"] == "admin"


def test_bootstrap_never_promotes_an_existing_account(db_session, bootstrap_settings):
    crud.create_user(db_session, schemas.UserCreate(email="boss@example.com", password="whatever123"))
    assert bootstrap.ensure_bootstrap_admin(db_session) == "exists"
    assert crud.get_user_by_email(db_session, "boss@example.com").role == models.Role.viewer


def test_bootstrap_email_cannot_be_pre_registered_as_a_viewer(client, bootstrap_settings):
    resp = _register(client, "BOSS@example.com")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Email already registered"  # same message as any taken address


def test_bootstrap_with_a_weak_password_fails_loudly_not_a_dead_admin(db_session, monkeypatch):
    monkeypatch.setattr(settings, "BOOTSTRAP_ADMIN_EMAIL", "boss@example.com")
    monkeypatch.setattr(settings, "BOOTSTRAP_ADMIN_PASSWORD", "short")
    with pytest.raises(ValueError):
        bootstrap.ensure_bootstrap_admin(db_session)
    assert crud.list_users(db_session) == []


# ---- secret guard ------------------------------------------------------------------------

def test_default_secret_refused_outside_local_env():
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(ICOP_ENV="production", SECRET_KEY="dev-secret-change-me")


def test_short_secret_refused_outside_local_env():
    with pytest.raises(ValueError, match="32 bytes"):
        Settings(ICOP_ENV="staging", SECRET_KEY="short")


def test_strong_secret_accepted_outside_local_env():
    assert Settings(ICOP_ENV="production", SECRET_KEY="k" * 48).ICOP_ENV == "production"
