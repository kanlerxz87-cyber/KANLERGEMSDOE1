#!/usr/bin/env python3
"""Refresh a public-source availability feed; do not scrape or infer scores."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "docs/data/feed-sources.json"
DEFAULT_OUTPUT = ROOT / "docs/data/live-source-status.json"
MAX_BODY_BYTES = 2_000_000
USER_AGENT = "KANLERGEMSDOE1-public-source-monitor/1.0"


class _TitleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_title = False
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._chunks.append(data)

    @property
    def title(self) -> str:
        return " ".join(" ".join(self._chunks).split())[:300]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _is_login_redirect(final_url: str, title: str) -> bool:
    path = urlsplit(final_url).path.lower().rstrip("/")
    return path.endswith("/accounts/login") or title.strip().lower() == "login"


def _result_base(source: dict[str, Any], observed_at: str) -> dict[str, Any]:
    return {
        "id": source["id"],
        "label": source["label"],
        "kind": source["kind"],
        "url": source["url"],
        "observed_at_utc": observed_at,
        "status": "not_checked",
        "http_status": None,
        "final_url": None,
        "title": None,
        "content_sha256": None,
        "hashed_bytes": 0,
        "content_truncated": False,
        "note": None,
    }


def probe_source(source: dict[str, Any], timeout: float = 20.0) -> dict[str, Any]:
    """Record public-page availability and a content fingerprint only.

    The response body is not persisted and page text is never searched for scores,
    predictions, upload links, or approval language. A login redirect is recorded
    as such, not treated as an accessible dataset.
    """
    observed_at = _utc_now()
    result = _result_base(source, observed_at)
    request = Request(source["url"], headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})

    try:
        with urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", None)
            if status is None:
                status = response.getcode()
            final_url = response.geturl()
            body = response.read(MAX_BODY_BYTES + 1)
            truncated = len(body) > MAX_BODY_BYTES
            if truncated:
                body = body[:MAX_BODY_BYTES]
    except HTTPError as exc:
        status = exc.code
        final_url = exc.geturl()
        body = exc.read(MAX_BODY_BYTES + 1)
        truncated = len(body) > MAX_BODY_BYTES
        if truncated:
            body = body[:MAX_BODY_BYTES]
    except (URLError, TimeoutError, OSError) as exc:
        result["status"] = "network_error"
        result["note"] = str(getattr(exc, "reason", exc))[:300]
        return result
    except Exception as exc:  # Keep one flaky source from hiding the other probes.
        result["status"] = "probe_error"
        result["note"] = f"{type(exc).__name__}: {exc}"[:300]
        return result

    parser = _TitleParser()
    try:
        parser.feed(body.decode("utf-8", errors="replace"))
    except Exception:
        pass
    title = parser.title or None

    result.update(
        {
            "http_status": status,
            "final_url": final_url,
            "title": title,
            "content_sha256": hashlib.sha256(body).hexdigest(),
            "hashed_bytes": len(body),
            "content_truncated": truncated,
        }
    )
    if _is_login_redirect(final_url, title or ""):
        result["status"] = "login_required"
        result["note"] = "Public page redirected to a login form; no authenticated content was requested."
    elif isinstance(status, int) and 200 <= status < 300:
        result["status"] = "ok"
    else:
        result["status"] = "http_error"
        result["note"] = f"Public page returned HTTP {status}."
    return result


def refresh(catalog_path: Path, output_path: Path, timeout: float = 20.0) -> dict[str, Any]:
    sources = json.loads(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(sources, list):
        raise ValueError("Source catalog must be a JSON list")
    seen_ids: set[str] = set()
    for source in sources:
        if not isinstance(source, dict) or not {"id", "label", "kind", "url"}.issubset(source):
            raise ValueError("Every source entry must contain id, label, kind, and url")
        source_id = str(source["id"])
        parsed_url = urlsplit(str(source["url"]))
        if source_id in seen_ids:
            raise ValueError(f"Duplicate source id: {source_id}")
        if parsed_url.scheme != "https" or not parsed_url.hostname:
            raise ValueError(f"Source URLs must be absolute HTTPS URLs: {source_id}")
        seen_ids.add(source_id)

    generated_at = _utc_now()
    results = [probe_source(source, timeout=timeout) for source in sources]
    payload = {
        "schema_version": "1.0",
        "generated_at_utc": generated_at,
        "purpose": "Public-source availability and content fingerprints only; not a score feed, quality audit, scientific validation, or submission approval.",
        "scores_scraped": False,
        "upload_or_submission_actions_performed": False,
        "sources": results,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG, help="JSON list of public page URLs")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Path for the generated status JSON")
    parser.add_argument("--timeout", type=float, default=20.0, help="Per-request timeout in seconds")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    payload = refresh(args.catalog, args.output, args.timeout)
    print(f"Wrote {len(payload['sources'])} public-source status records to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
