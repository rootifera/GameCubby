"""
Authenticated requests must reuse the request's own DB session to read the JWT secret
instead of opening a second one (an extra pool connection + pre-ping on every request).
"""
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from gamecubby_api.models import Base
from gamecubby_api.models.admin import AdminUser
from gamecubby_api.models.app_config import AppConfig
from gamecubby_api.utils import auth, jwt


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(AppConfig(key="SECRET_KEY", value="test-secret"))
    session.add(AdminUser(id=1, username="admin", password_hash="x"))
    session.commit()

    def _forbidden():
        raise AssertionError("opened a second DB session (with_db) instead of reusing the request's")

    monkeypatch.setattr(jwt, "with_db", _forbidden)
    return session


def _creds(token):
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_get_current_admin_uses_the_request_session(db):
    token = jwt.create_access_token({"sub": "1", "role": "admin"}, db)
    assert auth.get_current_admin(_creds(token), db).username == "admin"


def test_get_current_admin_optional_uses_the_request_session(db):
    token = jwt.create_access_token({"sub": "1", "role": "admin"}, db)
    assert auth.get_current_admin_optional(_creds(token), db).username == "admin"
    assert auth.get_current_admin_optional(_creds("garbage"), db) is None


def test_bad_token_and_non_admin_are_still_rejected(db):
    with pytest.raises(HTTPException) as bad:
        auth.get_current_admin(_creds("not.a.jwt"), db)
    assert bad.value.status_code == 401
    user_token = jwt.create_access_token({"sub": "1", "role": "user"}, db)
    with pytest.raises(HTTPException) as nope:
        auth.get_current_admin(_creds(user_token), db)
    assert nope.value.status_code == 403


def test_a_token_signed_with_another_secret_is_rejected(db):
    forged = jwt.jwt.encode({"sub": "1", "role": "admin"}, "some-other-secret", algorithm=jwt.ALGORITHM)
    with pytest.raises(HTTPException) as e:
        auth.get_current_admin(_creds(forged), db)
    assert e.value.status_code == 401
