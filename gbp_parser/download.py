"""Download original photo files into data/<place folder>/photos/."""
import hashlib
import time
import urllib.error
import urllib.request

from . import config

EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
ATTEMPTS = 3


def _fetch(url):
    for attempt in range(1, ATTEMPTS + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.read(), response.headers.get_content_type()
        except (urllib.error.URLError, TimeoutError):
            if attempt == ATTEMPTS:
                raise
            time.sleep(2 * attempt)


def download_original(url, folder, uploaded_at, google_id):
    """Save the full-size file; return (path relative to data/, size in bytes, sha256)."""
    data, content_type = _fetch(url + "=s0")
    date = uploaded_at.strftime("%Y-%m-%d_%Hh") if uploaded_at else "undated"
    relative = f"{folder}/photos/{date}_{google_id}{EXTENSIONS.get(content_type, '.bin')}"
    path = config.DATA_DIR / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return relative, len(data), hashlib.sha256(data).hexdigest()
