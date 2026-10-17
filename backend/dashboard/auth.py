"""Passwords (scrypt, from the standard library) and random tokens for sessions and QR pairings."""
import hashlib
import hmac
import re
import secrets

from backend import settings

SCRYPT = {"n": 2**14, "r": 8, "p": 1}
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def hash_password(password):
    """'scrypt$<salt hex>$<hash hex>'."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def check_password(password, stored):
    """True if `password` matches a hash from hash_password (compared in constant time)."""
    try:
        _, salt, digest = stored.split("$")
        attempt = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), **SCRYPT)
    except ValueError:
        return False
    return hmac.compare_digest(attempt.hex(), digest)


def account_problem(name, email, password):
    """What's wrong with a sign-up form in plain words, or None."""
    if not name:
        return "Please enter your name."
    if not EMAIL.match(email):
        return "Please enter a valid email address: notifications are sent there."
    if len(password) < settings.MIN_PASSWORD_LEN:
        return f"Please choose a password of at least {settings.MIN_PASSWORD_LEN} characters."
    return None


def new_token():
    """(token for the cookie or QR code, its hash for the database)."""
    token = secrets.token_urlsafe(32)
    return token, token_hash(token)


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()
