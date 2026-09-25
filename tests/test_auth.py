import jwt
from app.config import settings
from app.security import (
    create_access_token,
    get_password_hash,
    verify_password,
)


def test_password_hashing():
    raw_pass = "EnterpriseBankingSecurePass#2024"
    hashed = get_password_hash(raw_pass)

    assert hashed != raw_pass
    assert verify_password(raw_pass, hashed) is True
    assert verify_password("wrong_password", hashed) is False


def test_create_and_decode_jwt():
    username = "compliance_officer_1"
    token = create_access_token(data={"sub": username})

    payload = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
    )

    assert payload.get("sub") == username
    assert "exp" in payload
    assert "iat" in payload
