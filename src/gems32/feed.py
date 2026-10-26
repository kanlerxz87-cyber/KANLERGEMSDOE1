"""The site's machine-readable feed.

Everything the site shows that can change -- build state, hypotheses, the holdout summary, the
leaderboard snapshot, source health -- is assembled here, so the published page is always a
rendering of the repository rather than something a human retyped.

Score discipline: an owner-reported number is stored with ``"kind": "owner_report"`` and is never
rendered next to a verified number without that label; leaderboard rows carry ``verified: true``
only when they were read from the public page in the same run that stored them.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP_PROBE = ("drivendata.org",)      # standing brief: never automate access to the competition host


def _read_json(p: Path, default=None):
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


def sha256(path: Path, limit: int | None = None) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def build(root: Path = ROOT) -> dict:
    reg, docs = root / "registry", root / "docs"
    feed: dict = {"schema": 1, "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    src = _read_json(reg / "sources.json", {"sources": []})
    feed["sources"] = src["sources"]
    feed["source_count"] = len(src["sources"])

    rows = []
    lb_path = reg / "leaderboard_history.jsonl"
    if lb_path.exists():
        for line in lb_path.read_text().splitlines():
            if line.strip():
                rows.append(json.loads(line))
    feed["leaderboard"] = rows[-1]["rows"] if rows else []
    feed["leaderboard_observed_utc"] = rows[-1].get("observed_utc") if rows else None
    feed["leaderboard_verified"] = bool(rows and rows[-1].get("verified"))
    feed["leaderboard_snapshots"] = len(rows)

    hyp = _read_json(reg / "hypotheses.json", {"hypotheses": []})
    feed["hypotheses"] = hyp["hypotheses"]

    claims = _read_json(reg / "claims.json", {"claims": []})
    feed["claims"] = claims["claims"]

    sub = _read_json(reg / "submission_build.json")
    if sub:
        feed["submission"] = sub
        f = sub.get("file", {})
        fp = root / f.get("path", "")
        f["sha256"] = f.get("sha256") or (sha256(fp) if fp.is_file() else None)
        f["bytes"] = f.get("bytes") or (fp.stat().st_size if fp.is_file() else None)
    hold = _read_json(root / "evidence" / "holdout_run1.json")
    if hold:
        def _arms(f):
            a = f.get("arms", {})
            if isinstance(a, dict):
                return {k: {"dti": v.get("dti"), "n_px": v.get("n_px")} for k, v in a.items()}
            return {v["name"]: {"dti": v.get("dti"), "n_px": v.get("n_px")} for v in a}
        feed["holdout"] = {"preregistration": hold["preregistration"]["id"],
                           "summary": hold["summary"], "generated_utc": hold.get("generated_utc"),
                           "folds": [{"block": f.get("block"), "auc": f.get("auc"),
                                      "n_truth": f.get("n_truth", 0), "arms": _arms(f)}
                                     for f in hold["folds"]]}
    for name in ("h60_2_catalogue_difference.json", "truth_model_mc.json",
                 "emission_models_mc.json", "shipped_vs_incumbent_mc.json",
                 "h44_spcp_run_card.json", "nine_site_live_audit_20261026.json"):
        ev = _read_json(root / "evidence" / name)
        if ev:
            feed.setdefault("evidence", {})[name] = ev
    cs = _read_json(reg / "current_status.json")
    if cs:
        feed["current_status"] = cs
    feed["irregularities"] = _read_json(reg / "irregularities.json", {"items": []})["items"]
    (docs / "data").mkdir(parents=True, exist_ok=True)
    feed_path = docs / "data" / "feed.json"
    prev = _read_json(feed_path)
    if isinstance(prev, dict) and "generated_utc" in prev:
        cmp_prev = {k: v for k, v in prev.items() if k != "generated_utc"}
        cmp_curr = {k: v for k, v in feed.items() if k != "generated_utc"}
        if cmp_prev == cmp_curr:
            feed["generated_utc"] = prev["generated_utc"]
    feed_path.write_text(json.dumps(feed, indent=1) + "\n")
    return feed


def refresh_sources(root: Path = ROOT, timeout: float = 15.0) -> dict:
    """Probe every *non-competition* source once and record the observed status.

    Sources on ``SKIP_PROBE`` (the competition host) are recorded as ``not_probed``: the standing
    brief is explicit that access to the competition site is never automated.
    """
    import urllib.request
    results = []
    src = _read_json(root / "registry" / "sources.json", {"sources": []})
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for s in src["sources"]:
        url = s["url"]
        rec = {"id": s["id"], "url": url, "checked_utc": now}
        if any(h in url for h in SKIP_PROBE):
            rec.update(status="not_probed", note="competition host: never probed automatically")
            results.append(rec)
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "GEMSDOE32-feed/1.0 (+research)"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                rec.update(http_status=int(r.status), content_type=r.headers.get("Content-Type", ""))
        except Exception as exc:                      # noqa: BLE001 - recorded, never raised
            rec.update(http_status=None, error=f"{type(exc).__name__}: {exc}")
        results.append(rec)
    out = {"checked_utc": now, "results": results,
           "policy": "drivendata.org is never requested by this repository"}
    (root / "docs" / "data").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "data" / "source_health.json").write_text(json.dumps(out, indent=1) + "\n")
    return out
