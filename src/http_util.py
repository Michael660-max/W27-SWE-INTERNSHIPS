from __future__ import annotations

import time
from typing import Optional

import httpx

from .config import HTTP_RETRIES, HTTP_TIMEOUT, USER_AGENT


def get_client(timeout: float | None = None) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
        timeout=timeout or HTTP_TIMEOUT,
        follow_redirects=True,
    )


def fetch_text(url: str, client: Optional[httpx.Client] = None) -> str:
    owns = client is None
    client = client or get_client()
    last_err: Exception | None = None
    try:
        for attempt in range(HTTP_RETRIES + 1):
            try:
                resp = client.get(url)
                resp.raise_for_status()
                return resp.text
            except Exception as exc:
                last_err = exc
                if attempt < HTTP_RETRIES:
                    time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"Failed to fetch {url}: {last_err}")
    finally:
        if owns:
            client.close()


def fetch_json(url: str, client: Optional[httpx.Client] = None):
    owns = client is None
    client = client or get_client()
    try:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.json()
    finally:
        if owns:
            client.close()


def head_or_get_ok(url: str, client: Optional[httpx.Client] = None) -> tuple[bool, int, str]:
    """Return (ok, status_code, final_url). Soft-fail friendly."""
    if not url:
        return False, 0, ""
    owns = client is None
    client = client or get_client()
    try:
        try:
            resp = client.head(url)
            if resp.status_code >= 400 or resp.status_code == 405:
                resp = client.get(url)
        except Exception:
            resp = client.get(url)
        text_snippet = ""
        if resp.status_code < 400 and "text" in (resp.headers.get("content-type") or ""):
            text_snippet = resp.text[:4000].lower()
        closed_markers = (
            "no longer accepting",
            "job not found",
            "position has been filled",
            "this job is closed",
            "page not found",
            "404",
        )
        if resp.status_code >= 400:
            return False, resp.status_code, str(resp.url)
        if any(m in text_snippet for m in closed_markers):
            return False, resp.status_code, str(resp.url)
        return True, resp.status_code, str(resp.url)
    except Exception:
        return False, 0, url
    finally:
        if owns:
            client.close()
