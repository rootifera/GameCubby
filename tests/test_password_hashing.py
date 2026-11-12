"""Password hashing uses bcrypt directly (passlib was dropped).

The fixtures below are hashes that the previous passlib + bcrypt 4.0.1 stack produced, so
these tests prove existing admin passwords keep working after the switch.
"""
import pytest

from gamecubby_api.utils.auth import hash_password, verify_password

# (id, password, hash made by passlib 1.7.4 + bcrypt 4.0.1)
LEGACY_PASSLIB_HASHES = [
    ('short', 'hunter2', '$2b$12$1BTxdEuca0XUSwoXoUWJCeQEIHdi4/h/30isnBWRISDC6F7qwvIZm'),
    ('long80', 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA', '$2b$12$J/2ddkfjjdeZsTE/Ixg0Me1LbmFD5BN86dTGPGxS5kICSemOJ6VAi'),
    ('unicode', 'pässwörd-日本語', '$2b$12$ixCLmOpKMKmXzDjv6Q1L8.42/1StZlWb514AopnA8PhOi/LdonG9O'),
    ('exact72', 'BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB', '$2b$12$UDA2gNbnVUqD5uYp2qgnV.VYMSJ.74y0Q8XgjlvY40dMh09ZNH/dK'),
    ('spaces', '  padded pw  ', '$2b$12$Kyx6tJ0raAfsx6x2ZJjlQu9tb2Us/dUzUSfNvex67ekystylcECxe'),
]


@pytest.mark.parametrize("_id,password,legacy_hash", LEGACY_PASSLIB_HASHES, ids=[c[0] for c in LEGACY_PASSLIB_HASHES])
def test_legacy_passlib_hashes_still_verify(_id, password, legacy_hash):
    assert verify_password(password, legacy_hash) is True
    assert verify_password("!" + password, legacy_hash) is False


def test_passwords_longer_than_72_bytes_behave_like_passlib():
    # passlib silently truncated to 72 bytes; bcrypt >= 5 raises. We truncate ourselves.
    legacy_hash = next(h for i, _, h in LEGACY_PASSLIB_HASHES if i == "long80")
    assert verify_password("A" * 80, legacy_hash) is True
    assert verify_password("A" * 72, legacy_hash) is True


def test_hash_and_verify_roundtrip():
    hashed = hash_password("correct horse battery staple")
    assert hashed.startswith("$2b$")
    assert verify_password("correct horse battery staple", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_long_password_roundtrip_does_not_raise():
    hashed = hash_password("x" * 200)
    assert verify_password("x" * 200, hashed) is True


@pytest.mark.parametrize("bad_hash", ["", "not-a-hash", "$2b$12$tooshort"])
def test_malformed_hash_is_a_mismatch_not_an_error(bad_hash):
    assert verify_password("anything", bad_hash) is False
