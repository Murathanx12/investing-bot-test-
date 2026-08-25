"""One small HTTP helper so every adapter shares a timeout and a user agent."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

UA = "aegis-alpha-terminal/0.2 (research; mrthnabdullaev@gmail.com)"


class SourceRefusal(RuntimeError):
    """The source did not answer, or answered with something we will not use."""


def get_json(url: str, params: dict[str, Any] | None = None, *, headers: dict | None = None,
             timeout: float = 20.0) -> tuple[Any, float]:
    """GET -> (parsed json, latency seconds). Raises SourceRefusal on any failure."""
    if params:
        clean = {k: v for k, v in params.items() if v is not None}
        url = f"{url}?{urllib.parse.urlencode(clean)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raise SourceRefusal(f"GET {url.split('?')[0]} -> HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SourceRefusal(f"GET {url.split('?')[0]} -> {exc}") from exc
    try:
        return json.loads(raw), time.time() - t0
    except json.JSONDecodeError as exc:
        raise SourceRefusal(f"GET {url.split('?')[0]} -> non-JSON body") from exc


def post_json(url: str, body: Any, *, headers: dict | None = None,
              timeout: float = 90.0) -> tuple[Any, float]:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), method="POST",
        headers={"User-Agent": UA, "Content-Type": "application/json", **(headers or {})},
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read()), time.time() - t0
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        raise SourceRefusal(f"POST {url} -> HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SourceRefusal(f"POST {url} -> {exc}") from exc
