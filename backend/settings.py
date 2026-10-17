"""Backend settings: ports, data folders, database and email.

Secrets and machine-specific values come from the .env file at the repository root (see .env.example), so no
password ever sits in the code. Voice-analysis settings live in voice_checker/config.py.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
ROOT = BACKEND_DIR.parent   # the repository
load_dotenv(ROOT / ".env")


def _env(name, default=""):
    return os.environ.get(name, default).strip()


def _flag(name, default):
    value = _env(name, str(default)).lower()
    return value in {"1", "true", "yes", "on"}


# --- Data folders (no audio is ever stored) ---------------------------------
DATA_DIR = BACKEND_DIR / "data"
CERT_DIR = DATA_DIR / "certs"       # self-signed HTTPS certificate for the phone pages
OUTBOX_DIR = DATA_DIR / "outbox"    # emails are saved here as .eml files when EMAIL_BACKEND=outbox

# --- Database ---------------------------------------------------------------
# postgresql://user:password@host:port/name (the Docker database, see docker-compose.yml), or
# sqlite:///path/to/file.db with the path relative to the repository.
DATABASE_URL = _env("DATABASE_URL", "sqlite:///backend/data/dashboard.db")

# --- Web app ----------------------------------------------------------------
# The Next.js app (frontend/). Email links point here, and the API accepts requests coming from it.
FRONTEND_URL = _env("FRONTEND_URL", "http://localhost:3000").rstrip("/")

# --- Phone link dashboard (python -m backend.dashboard) ---------------------
DASHBOARD_PORT = int(_env("DASHBOARD_PORT", "8700"))   # http://localhost:8700, reachable from this laptop only
PHONE_PORT = int(_env("PHONE_PORT", "8443"))           # https://<laptop Wi-Fi address>:8443
PAIRING_TTL_S = 300        # a QR code links one phone, within 5 minutes
LAPTOP_SESSION_DAYS = 7    # then sign in again on the laptop
PHONE_SESSION_DAYS = 30    # a linked phone stays linked this long, unless disconnected
MIN_PASSWORD_LEN = 8
MAX_UPLOAD_MB = 25         # the phone sends 16 kHz mono WAV: about 13 minutes

# --- Email ------------------------------------------------------------------
EMAIL_BACKEND = _env("EMAIL_BACKEND", "outbox").lower()   # "smtp" sends; "outbox" saves .eml files in OUTBOX_DIR
EMAIL_FROM = _env("EMAIL_FROM")                           # "Name <address>"; the address must be a verified sender
SMTP_HOST = _env("SMTP_HOST")
SMTP_PORT = int(_env("SMTP_PORT", "587"))
SMTP_STARTTLS = _flag("SMTP_STARTTLS", True)              # port 587: plain connection upgraded with STARTTLS
SMTP_SSL = _flag("SMTP_SSL", False)                       # port 465: TLS from the start
SMTP_USERNAME = _env("SMTP_USERNAME")
SMTP_PASSWORD = _env("SMTP_PASSWORD")
