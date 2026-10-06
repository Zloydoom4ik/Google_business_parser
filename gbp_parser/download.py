"""Download original picture files into data/<place folder>/photos/ or .../posts/."""
import hashlib
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import config

EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
ATTEMPTS = 3
WORKERS = 8         # files downloaded at the same time


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


def download_original(url, folder, uploaded_at, google_id, subfolder="photos"):
    """Save the full-size file; return (path relative to data/, size in bytes, sha256)."""
    data, content_type = _fetch(url + "=s0")
    date = uploaded_at.strftime("%Y-%m-%d_%Hh") if uploaded_at else "undated"
    relative = f"{folder}/{subfolder}/{date}_{google_id}{EXTENSIONS.get(content_type, '.bin')}"
    path = config.DATA_DIR / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return relative, len(data), hashlib.sha256(data).hexdigest()


def download_all(rows, folder, url_column, date_column, subfolder="photos"):
    """Download the originals for database rows, WORKERS at a time.

    Yields (row, path relative to data/, size in bytes, sha256) as each file finishes, in no fixed order.
    """
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        jobs = {pool.submit(download_original, row[url_column], folder, row[date_column], row["google_id"],
                            subfolder): row for row in rows}
        for job in as_completed(jobs):
            yield (jobs[job], *job.result())
