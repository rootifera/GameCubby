"""
Login tokens are bound to the password they were issued for: changing the password invalidates
every older session, and a token forged with a leaked SECRET_KEY is useless without the
current password hash's fingerprint.
"""
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from jose import jwt as jose_jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from gamecubby_api.models import Base
from gamecubby_api.models.admin import AdminUser
from gamecubby_api.models.app_config import AppConfig
from gamecubby_api.routers import auth as auth_router
from gamecubby_api.utils import auth, jwt


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(AppConfig(key="SECRET_KEY", value="test-secret"))
    session.add(AdminUser(id=1, username="admin", password_hash=auth.hash_password("old-password")))
    session.commit()
    monkeypatch.setattr(jwt, "with_db", lambda: (_ for _ in ()).throw(AssertionError("second session")))
    return session


def _token(db, **extra):
    user = db.query(AdminUser).first()
    payload = {"sub": "1", "role": "admin", "pwv": auth.password_fingerprint(user.password_hash), **extra}
    return jwt.create_access_token(payload, db)


def _creds(token):
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_a_fresh_token_works_and_the_fingerprint_is_stable(db):
    token = _token(db)
    assert auth.get_current_admin(_creds(token), db).username == "admin"
    user = db.query(AdminUser).first()
    assert auth.password_fingerprint(user.password_hash) == auth.password_fingerprint(user.password_hash)


def test_changing_the_password_invalidates_every_older_token(db):
    old = _token(db)
    user = db.query(AdminUser).first()
    auth_router.change_password(
        type("D", (), {"current_password": "old-password", "new_password": "a-new-password"})(), user, db)

    with pytest.raises(HTTPException) as e:
        auth.get_current_admin(_creds(old), db)
    assert e.value.status_code == 401 and "log in again" in e.value.detail
    assert auth.get_current_admin_optional(_creds(old), db) is None
    assert auth.get_current_admin(_creds(_token(db)), db).username == "admin", "a new login works"


def test_change_password_tells_the_client_to_log_in_again(db):
    user = db.query(AdminUser).first()
    result = auth_router.change_password(
        type("D", (), {"current_password": "old-password", "new_password": "a-new-password"})(), user, db)
    assert result["relogin_required"] is True


def test_a_token_without_the_fingerprint_is_rejected(db):
    legacy = jwt.create_access_token({"sub": "1", "role": "admin"}, db)  # what pre-3.4.3 logins looked like
    with pytest.raises(HTTPException) as e:
        auth.get_current_admin(_creds(legacy), db)
    assert e.value.status_code == 401


def test_a_forged_token_fails_even_with_the_leaked_secret_key_after_a_password_change(db):
    """The leaked-database scenario: attacker has SECRET_KEY and the OLD password hash."""
    old_hash = db.query(AdminUser).first().password_hash
    forged = jose_jwt.encode({"sub": "1", "role": "admin", "pwv": auth.password_fingerprint(old_hash)}, "test-secret", algorithm="HS256")
    assert auth.get_current_admin(_creds(forged), db).username == "admin", "valid until the password changes"

    user = db.query(AdminUser).first()
    auth_router.change_password(
        type("D", (), {"current_password": "old-password", "new_password": "a-new-password"})(), user, db)

    with pytest.raises(HTTPException) as e:
        auth.get_current_admin(_creds(forged), db)
    assert e.value.status_code == 401


def test_a_wrong_fingerprint_is_rejected(db):
    bad = jwt.create_access_token({"sub": "1", "role": "admin", "pwv": "0" * 16}, db)
    with pytest.raises(HTTPException):
        auth.get_current_admin(_creds(bad), db)
