"""공통 HTTP 세션. 공공 사이트에 부담을 주지 않도록 요청 간격을 두고, 받은 응답은 캐시한다."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / ".cache"
USER_AGENT = "Mozilla/5.0 (compatible; reg_tracker/0.1; +https://github.com/cafeon90-oss/reg_tracker)"
MIN_INTERVAL = 1.0  # 초. 같은 사이트에 연달아 요청할 때의 최소 간격

_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT
_last_request = 0.0


def _cache_path(method: str, url: str, params, data) -> Path:
    key = json.dumps([method, url, params, data], ensure_ascii=False, sort_keys=True)
    return CACHE_DIR / (hashlib.sha256(key.encode()).hexdigest()[:24])


def fetch(url: str, *, method: str = "GET", params=None, data=None, headers=None,
          cache: bool = True, timeout: int = 60) -> bytes:
    """응답 본문을 bytes로 돌려준다. cache=True면 같은 요청은 디스크에서 읽는다."""
    global _last_request
    path = _cache_path(method, url, params, data)
    if cache and path.exists():
        return path.read_bytes()

    wait = MIN_INTERVAL - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    for attempt in range(3):
        try:
            r = _session.request(method, url, params=params, data=data, headers=headers, timeout=timeout)
            _last_request = time.monotonic()
            r.raise_for_status()
            break
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))

    if cache:
        CACHE_DIR.mkdir(exist_ok=True)
        path.write_bytes(r.content)
    return r.content


def fetch_text(url: str, **kw) -> str:
    return fetch(url, **kw).decode("utf-8", errors="replace")
