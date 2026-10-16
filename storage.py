"""Storage: one JSON file per user in data/users/, holding all of their sessions."""
import json
import re

import config


def user_file(name):
    """Path of a user's JSON file; the name is turned into a safe file name."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-") or "user"
    return config.USERS_DIR / f"{slug}.json"


def load_user(name):
    """Return {"name", "sessions"}; an empty record if the user is new."""
    path = user_file(name)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"name": name.strip(), "sessions": []}


def save_user(user):
    """Write the whole user record back to disk."""
    path = user_file(user["name"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(user, indent=1), encoding="utf-8")


def add_session(name, session):
    """Append a session to a user's file and return the updated user."""
    user = load_user(name)
    user["sessions"].append(session)
    save_user(user)
    return user


def sessions_for_text(user, text_id):
    """A user's sessions for one text, oldest first."""
    return sorted((s for s in user["sessions"] if s["text_id"] == text_id), key=lambda s: s["timestamp"])


def list_users():
    """Names of every stored user."""
    return sorted(json.loads(p.read_text(encoding="utf-8"))["name"] for p in config.USERS_DIR.glob("*.json"))
