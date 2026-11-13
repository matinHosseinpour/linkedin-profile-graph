"""Small shared helpers. JSON is UTF-8; dates are UTC ISO-8601."""

import json
import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit


def utc_now():
    return datetime.now(UTC).isoformat(timespec="seconds")


def clean(value):
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    if not text or text.casefold() in {"linkedin member", "private", "hidden", "***", "—"}:
        return None
    return text


def normalize(value):
    return unicodedata.normalize("NFKC", clean(value) or "").casefold()


def safe_url(value, base="https://www.linkedin.com"):
    """Remove tracking queries/fragments; disallow executable links and URL credentials."""
    if not value:
        return None
    parts = urlsplit(urljoin(base, str(value)))
    if parts.scheme not in {"https", "http"} or not parts.hostname or parts.username:
        return None
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def profile_url(value):
    """Canonical HTTPS profile URL; no arbitrary URLs or authenticated endpoints."""
    parts = urlsplit(str(value))
    if (
        parts.scheme != "https"
        or parts.hostname not in {"linkedin.com", "www.linkedin.com"}
        or parts.username
        or parts.password
        or parts.port not in {None, 443}
        or not re.fullmatch(r"/in/[^/]+/?", parts.path)
        or re.search(r"[\s/\\?#]", unquote(parts.path.removeprefix("/in/").rstrip("/")))
    ):
        raise ValueError("Expected https://www.linkedin.com/in/<profile-slug>/")
    return f"https://www.linkedin.com{parts.path.rstrip('/')}"


def dump_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def unique(items, key):
    seen = set()
    result = []
    for item in items:
        identity = key(item)
        if identity not in seen:
            seen.add(identity)
            result.append(item)
    return result
