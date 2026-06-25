import hashlib
import os
import time
import jwt
from server.config import JWT_SECRET, JWT_EXPIRE_DAYS


def hash_pin(pin: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, 100000)
    return salt.hex() + ":" + dk.hex()


def verify_pin(pin: str, stored_hash: str) -> bool:
    parts = stored_hash.split(":")
    if len(parts) != 2:
        return False
    salt = bytes.fromhex(parts[0])
    expected_dk = parts[1]
    dk = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, 100000)
    return dk.hex() == expected_dk


def create_token(qq: int) -> str:
    payload = {
        "qq": qq,
        "exp": int(time.time()) + JWT_EXPIRE_DAYS * 86400,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
