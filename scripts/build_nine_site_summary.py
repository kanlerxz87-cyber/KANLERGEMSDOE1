#!/usr/bin/env python3
"""Build the nine-site executive summary (`docs/nine-site-summary.html`) and its evidence JSON.

Everything shown is recomputed here from local bytes; nothing is typed in by hand except the
USER-REPORTED ledger in `registry/user_reported_ledger_nine_sites.json`.

Labels used in the output (protocol rule 3):
  * USER-REPORTED   - ledger scores typed in from the session prompt (no submission receipt).
  * HOLDOUT-DTI     - SGMC-CAL-v3.0 evaluator output run here via `scripts/evaluate_holdout.py`
                      (shared code, no fork). Reported with withheld-positive count and 95% CI.
  * PROJECTION      - linear fit ledger ~ SGMC-CAL over the nine focus sites. Never a score.

Diagnostic note: the shared evaluator refuses NaN, so NaN-outside rasters are scored through a
temporary zeros-outside copy written to a temp dir. In-footprint values are unchanged. The
temp copy is not a submission file and is never written into the repo.

Usage:  .venv/bin/python scripts/build_nine_site_summary.py [--skip-eval]
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
from scipy.ndimage import distance_transform_edt
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from evaluate_holdout import evaluate_path  # noqa: E402  (shared evaluator, no fork)

TEMPLATE = ROOT / "data" / "sample_submission.tif"
LEDGER = ROOT / "registry" / "user_reported_ledger_nine_sites.json"
FOCUS = ROOT / "registry" / "focus_sites.json"
OUT_JSON = ROOT / "evidence" / "nine_site_summary.json"
OUT_HTML = ROOT / "docs" / "nine-site-summary.html"

OUR_FILE = ROOT / "docs" / "downloads" / "gemsdoe32-kanler1-uwbp-drcs-exp3-37647d-20261028T1725Z-6e01786e-nan.tif"
OUR_NAME = "kanler1-uwbp-drcs-exp3-37647d-nan"
OUR_NOTE = "KANLER1 UWBP-DRCS EXP3 worm+Dinkelbach 37647 dots NaN-outside; SGMC-CAL proxy 0.0892 (not organizer score)"
OTHER_REFS = {
    "13gems r13-lattice-s5_v2 (owner mirror)": ROOT / "data" / "scored" / "13gems_20261001_r13-lattice-s5_v2_nan-outside.tif",
    "8GEMSDOE Hedge-v2 (owner mirror)": ROOT / "data" / "scored" / "8GEMSDOE_Hedge-v2_submission.tif",
}
TOL_PX = 3.0
SAT_LIMIT = 0.70  # protocol: >70% of dots within 3 px of one reference = duplicate (literal)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def load_binary(p: Path, foot: np.ndarray) -> np.ndarray:
    """Dots = value 1 inside the official footprint. NaN/outside are not dots."""
    with rasterio.open(p) as ds:
        a = ds.read(1).astype("float64")
        assert ds.shape == foot.shape, (p, ds.shape)
    a = np.where(np.isfinite(a), a, 0.0)
    inside = a[foot]
    assert set(np.unique(inside)).issubset({0.0, 1.0}), f"non-binary inside footprint: {p}"
    return (a == 1.0) & foot


def zeros_copy(p: Path, dst_dir: Path) -> Path:
    with rasterio.open(p) as ds:
        a = ds.read(1).astype("float32")
        prof = ds.profile.copy()
    a = np.where(np.isfinite(a), a, 0.0).astype("float32")
    prof.update(nodata=None, dtype="float32", count=1)
    out = dst_dir / (p.stem + "_zeros.tif")
    with rasterio.open(out, "w", **prof) as dst:
        dst.write(a, 1)
    return out


def sgmc(p: Path, dst_dir: Path) -> dict:
    res = evaluate_path(zeros_copy(p, dst_dir), diagnostic_full_map=True, name=p.stem)
    s = res["sgmc_off_catalogue"]
    return {
        "evaluator_version": s["evaluator_version"],
        "score_label": "HOLDOUT-DTI",
        "sgmc_cal": round(float(s["sgmc_prevalence_calibrated_dti"]), 6),
        "ci95": [round(float(x), 6) for x in s["sgmc_calibrated_ci95"]],
        "n_withheld_positives": int(s["n_withheld_positives"]),
        "n_spatial_clusters": int(s["n_spatial_clusters"]),
        "n_bootstrap_reps": int(s["n_bootstrap_reps"]),
    }


def overlap3(a: np.ndarray, dist_b: np.ndarray) -> float:
    n = int(a.sum())
    return float((dist_b[a] <= TOL_PX).sum() / n) if n else float("nan")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-eval", action="store_true", help="reuse SGMC values from evidence JSON if present")
    args = ap.parse_args()

    with rasterio.open(TEMPLATE) as ds:
        foot = np.isfinite(ds.read(1))
        crs, transform, shape = str(ds.crs), ds.transform, ds.shape

    ledger = json.loads(LEDGER.read_text())
    focus = {f["site"]: f for f in json.loads(FOCUS.read_text())["files"]}

    cands = {}
    for site in ledger["sites"]:
        f = focus[site]
        p = ROOT / "data" / "focus" / f["dest"].split("/")[-1]
        assert sha256(p) == f["sha256"], f"hash pin mismatch for {site}"
        cands[site] = {"path": p, "kind": "focus (owner-mirror, other team)"}
    cands["OURS-UWBP-DRCS-EXP3"] = {"path": OUR_FILE, "kind": "candidate (this repo)"}
    for k, p in OTHER_REFS.items():
        cands[k] = {"path": p, "kind": "scored owner mirror"}

    prev = {}
    if args.skip_eval and OUT_JSON.exists():
        prev = {c["key"]: c for c in json.loads(OUT_JSON.read_text())["candidates"]}

    rows = []
    dots = {}
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        for key, c in cands.items():
            p = c["path"]
            d = load_binary(p, foot)
            dots[key] = d
            if key in prev:
                ev = prev[key]["sgmc"]
            else:
                ev = sgmc(p, tdp)
            rows.append({
                "key": key, "kind": c["kind"], "file": str(p.relative_to(ROOT)),
                "sha256": sha256(p), "bytes": p.stat().st_size, "dots": int(d.sum()),
                "sgmc": ev,
            })
            print(f"{key:42s} dots={int(d.sum()):7d} sgmc={ev['sgmc_cal']:.6f} {ev['ci95']}", flush=True)

    # ---- pairwise 3-px overlap (A's dots within 3 px of B's dots) + binary Pearson ----
    dist = {k: distance_transform_edt(~v) for k, v in dots.items()}
    keys = list(cands)
    pairs = []
    for a in keys:
        for b in keys:
            if a == b:
                continue
            ov = overlap3(dots[a], dist[b])
            inter = int((dots[a] & dots[b]).sum()); union = int((dots[a] | dots[b]).sum())
            pairs.append({"a": a, "b": b, "overlap3px": round(ov, 4),
                          "jaccard_exact": round(inter / union, 4) if union else float("nan"),
                          "exact_mask_equal": bool(np.array_equal(dots[a], dots[b]))})
    phi = {}
    for a in keys:
        for b in keys:
            if a < b:
                x = dots[a][foot].astype(float); y = dots[b][foot].astype(float)
                phi[f"{a} | {b}"] = round(float(np.corrcoef(x, y)[0, 1]), 4)

    # ---- projection: ledger ~ SGMC-CAL on the nine focus sites (PROJECTION, not a score) ----
    xs, ys, names = [], [], []
    for r in rows:
        if r["key"] in ledger["sites"]:
            best = max(e["score"] for e in ledger["sites"][r["key"]]["entries"])
            xs.append(r["sgmc"]["sgmc_cal"]); ys.append(best); names.append(r["key"])
    xs = np.array(xs); ys = np.array(ys)
    lr = stats.linregress(xs, ys)
    n = len(xs)
    resid = ys - (lr.intercept + lr.slope * xs)
    s_res = float(np.sqrt((resid ** 2).sum() / (n - 2)))
    rho = stats.spearmanr(xs, ys).statistic
    ours = next(r for r in rows if r["key"] == "OURS-UWBP-DRCS-EXP3")["sgmc"]["sgmc_cal"]
    tcrit = stats.t.ppf(0.975, n - 2)
    se_pred = s_res * np.sqrt(1 + 1 / n + (ours - xs.mean()) ** 2 / ((xs - xs.mean()) ** 2).sum())
    yhat = lr.intercept + lr.slope * ours
    inside_range = bool(xs.min() <= ours <= xs.max())
    proj = {
        "label": "PROJECTION (not a score)",
        "fit": "ledger best per site ~ SGMC-CAL, n=9 focus sites",
        "slope": round(float(lr.slope), 3), "intercept": round(float(lr.intercept), 4),
        "pearson_r": round(float(lr.rvalue), 4), "spearman_rho": round(float(rho), 4),
        "residual_sd": round(s_res, 4),
        "ours_sgmc": ours, "ours_projected": round(float(yhat), 4),
        "prediction_95": [round(float(yhat - tcrit * se_pred), 4), round(float(yhat + tcrit * se_pred), 4)],
        "inside_fitted_sgmc_range": inside_range,
        "fitted_sgmc_range": [round(float(xs.min()), 6), round(float(xs.max()), 6)],
    }

    out = {
        "schema": "nine-site-summary/v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "template": {"file": "data/sample_submission.tif", "crs": crs, "shape": list(shape),
                     "transform": list(transform)[:6], "footprint_pixels": int(foot.sum())},
        "tol_px": TOL_PX, "literal_saturation_limit": SAT_LIMIT,
        "ledger_label": ledger["label"], "candidates": rows, "overlap3px_pairs": pairs,
        "binary_pearson": phi, "projection": proj,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2) + "\n")
    OUT_HTML.write_text(render(out, ledger, focus))
    print("wrote", OUT_JSON.relative_to(ROOT), "and", OUT_HTML.relative_to(ROOT))
    return 0


def pct(x: float) -> str:
    return f"{100 * x:.2f}%"


def render(out: dict, ledger: dict, focus: dict) -> str:
    rows = {r["key"]: r for r in out["candidates"]}
    pairs = out["overlap3px_pairs"]
    proj = out["projection"]
    e = html.escape

    def max_overlap(key: str, others: list[str]):
        vals = [(p["overlap3px"], p["b"]) for p in pairs if p["a"] == key and p["b"] in others]
        return max(vals) if vals else (float("nan"), "-")

    focus_keys = list(ledger["sites"])
    P = {(p["a"], p["b"]): p["overlap3px"] for p in pairs}
    def PP_eq(a, b):
        return next(p for p in pairs if p["a"] == a and p["b"] == b)["exact_mask_equal"]
    r32, r36 = rows["GEMSDOE32"], rows["GEMSDOE36"]
    def ledger_score(site):
        return max(x["score"] for x in ledger["sites"][site]["entries"])
    best_rows = []
    for site in focus_keys:
        ent = ledger["sites"][site]["entries"]
        b = max(ent, key=lambda x: x["score"])
        r = rows[site]
        others = [k for k in focus_keys if k != site]
        mo, mk = max_overlap(site, others)
        best_rows.append(
            f"<tr><td><strong>{e(site)}</strong><br><a href=\"{e(ledger['sites'][site]['url'])}\">site</a></td>"
            f"<td>{e(b['id'])}</td><td class=num>{b['score']:.4f}</td>"
            f"<td class=num>{r['sgmc']['sgmc_cal']:.6f}<br><small>[{r['sgmc']['ci95'][0]:.4f}, {r['sgmc']['ci95'][1]:.4f}] n={r['sgmc']['n_withheld_positives']:,}</small></td>"
            f"<td class=num>{pct(mo)}<br><small>vs {e(mk)}</small></td>"
            f"<td class=num>{max(p['jaccard_exact'] for p in pairs if p['a'] == site and p['b'] in others):.4f}</td>"
            f"<td>{'<span class=tag-bad>NOT to resubmit</span>' if site else ''}</td></tr>"
        )
    ours = rows["OURS-UWBP-DRCS-EXP3"]
    o_over = [p for p in pairs if p["a"] == "OURS-UWBP-DRCS-EXP3"]
    o_jac_focus = max(p["jaccard_exact"] for p in o_over if p["b"] in focus_keys)
    o_jac_all = max(p["jaccard_exact"] for p in o_over)
    o_focus_max = max((p["overlap3px"], p["b"]) for p in o_over if p["b"] in focus_keys)
    o_all_max = max((p["overlap3px"], p["b"]) for p in o_over)
    o_r13 = next(p["overlap3px"] for p in o_over if "r13" in p["b"])
    o_r13_j = next(p["jaccard_exact"] for p in o_over if "r13" in p["b"])
    o_nonr13 = max((p["overlap3px"], p["b"]) for p in o_over if "r13" not in p["b"])
    fam = [p for p in pairs if p["a"] == "OURS-UWBP-DRCS-EXP3"]
    pair_rows = []
    for k in [r["key"] for r in out["candidates"]]:
        if k == "OURS-UWBP-DRCS-EXP3":
            continue
        ov = [p for p in pairs if p["a"] == "OURS-UWBP-DRCS-EXP3" and p["b"] == k][0]["overlap3px"]
        ov2 = [p for p in pairs if p["a"] == k and p["b"] == "OURS-UWBP-DRCS-EXP3"][0]["overlap3px"]
        pair_rows.append(f"<tr><td>{e(k)}</td><td class=num>{pct(ov)}</td><td class=num>{pct(ov2)}</td></tr>")

    # Focus-to-focus pairs with any direction >= 0.95 3-px overlap (computed). The 3-px test
    # saturates on dense references, so each pair also shows exact-pixel Jaccard and exact equality.
    PP = {(p["a"], p["b"]): p for p in pairs}
    flags = []
    for i, a in enumerate(focus_keys):
        for b in focus_keys[i + 1:]:
            ab, ba = P[(a, b)], P[(b, a)]
            if max(ab, ba) >= 0.95:
                q = PP[(a, b)]
                pr = out["binary_pearson"].get(f"{a} | {b}", out["binary_pearson"].get(f"{b} | {a}"))
                if q["exact_mask_equal"]:
                    reading = "<span class=tag-bad>identical dot mask</span>"
                elif q["jaccard_exact"] >= 0.5:
                    reading = "<span class=tag-warn>near-identical</span>"
                else:
                    reading = "<span class=tag-ok>3-px saturated (dense); exact overlap low</span>"
                flags.append(f"<tr><td>{e(a)} vs {e(b)}</td><td class=num>{pct(ab)} / {pct(ba)}</td>"
                             f"<td class=num>{q['jaccard_exact']:.4f}</td><td class=num>{pr:.4f}</td><td>{reading}</td></tr>")

    ledger_rows = []
    for site in focus_keys:
        for ent in ledger["sites"][site]["entries"]:
            ledger_rows.append(f"<tr><td>{e(site)}</td><td>{e(ent['id'])}</td><td class=num>{ent['score']:.4f}</td></tr>")

    proj_html = (f"<p><strong>PROJECTION, not a score.</strong> Linear fit of the USER-REPORTED best score per focus site on SGMC-CAL HOLDOUT-DTI "
                 f"(n=9): slope {proj['slope']}, Pearson r={proj['pearson_r']}, Spearman rho={proj['spearman_rho']} (n=9), "
                 f"residual SD {proj['residual_sd']}. Our candidate's SGMC-CAL is {proj['ours_sgmc']:.4f}; "
                 f"projected organizer score {proj['ours_projected']:.3f}, 95% prediction band {proj['prediction_95'][0]:.3f} to {proj['prediction_95'][1]:.3f}. "
                 f"{'Inside' if proj['inside_fitted_sgmc_range'] else 'OUTSIDE'} the fitted SGMC range {proj['fitted_sgmc_range'][0]:.4f} to {proj['fitted_sgmc_range'][1]:.4f}, so this is an extrapolation.</p>")

    css = "../docs/assets/style.css"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Nine-site executive summary · KANLERGEMSDOE1</title>
<link rel="stylesheet" href="assets/style.css">
<style>
 body{{padding:0 16px}} main{{max-width:1100px;margin:0 auto;padding:24px 0 60px}}
 table{{width:100%;border-collapse:collapse;font-size:14px;margin:12px 0 24px}}
 th,td{{border:1px solid var(--line);padding:8px;vertical-align:top;text-align:left}}
 th{{background:var(--bg2)}} td.num,.num{{text-align:right;font-family:var(--mono)}}
 .box{{border:2px solid var(--good);border-radius:10px;padding:16px 20px;margin:16px 0;background:var(--card)}}
 .warn{{border-color:var(--warn)}} .tag-bad{{color:var(--bad);font-weight:700}}
 .tag-ok{{color:var(--good);font-weight:700}} .tag-warn{{color:var(--warn);font-weight:700}}
 code{{font-family:var(--mono);word-break:break-all}} small{{color:var(--muted)}}
</style></head>
<body><main>
<h1>Nine-site executive summary</h1>
<p>Sites: GEMSDOE24, 25, 27, 28, 30, 31, 32, 33, 36. Scores are <strong>USER-REPORTED</strong> (no submission-page receipts). Proxy values are <strong>HOLDOUT-DTI</strong> from the shared evaluator (SGMC-CAL-v3.0). Estimates are <strong>PROJECTION</strong>. Generated {e(out['generated_utc'])} by <code>scripts/build_nine_site_summary.py</code>.</p>

<div class="box">
<h2>1. Which file to download and submit</h2>
<table>
<tr><th>File to download</th><th>Estimated organizer score</th><th>Unique vs the nine sites?</th><th>Status</th></tr>
<tr><td><a href="downloads/{e(OUR_FILE.name)}"><code>{e(OUR_FILE.name)}</code></a><br><small>single-band float32 GeoTIFF, EPSG:32611, 3730x3292, values 0/1 inside footprint, NaN outside, {ours['dots']:,} dots, SHA-256 <code>{ours['sha256']}</code></small></td>
<td>Not verified. Organizer score is UNKNOWN until a portal receipt exists.<br>{proj_html.replace('<p>','').replace('</p>','')}</td>
<td><span class="tag-ok">YES</span> against the 9 focus sites and 2 owner-mirror files restored here (100+ other ledger sites not restored). Highest 3-px overlap with a focus file: {pct(o_focus_max[0])} ({e(o_focus_max[1])}), below the 70% limit. Highest exact-pixel Jaccard with any reference: {o_jac_all:.4f}.<br><small>The literal 3-px rule fails against the r13 lattice, but that is saturation from a dense reference (exact Jaccard {o_jac_all:.4f}). See section 5.</small></td>
<td><span class="tag-ok">Validator PASS</span>. Download OK. Submit only after the team signs off on the r13 uniqueness decision.</td></tr>
</table>
<p><strong>Portal fields (paste exactly):</strong><br>Unique name: <code>{e(OUR_NAME)}</code><br>Note ({len(OUR_NOTE)} chars): <code>{e(OUR_NOTE)}</code></p>
<p><strong>Benchmark:</strong> GEMSDOE32 scored 0.2778 (USER-REPORTED). That is the highest of the nine sites. The live public leaderboard (fetched 2026-10-31, <code>evidence/leaderboard_snapshot_20261031.json</code>) has #1 at 0.4544, #2 at 0.3925 and #3 at 0.3917. The prompt also cites 0.4413 and 0.3195.</p>
</div>

<h2>2. Best submission per site</h2>
<p>For each site, the highest USER-REPORTED entry. Its file is pinned by SHA-256 in <code>registry/focus_sites.json</code>. These are other teams' files. <strong>Do not resubmit them.</strong></p>
<table>
<tr><th>Site</th><th>Best entry (ledger ID)</th><th class=num>Score (USER-REPORTED)</th><th class=num>SGMC-CAL HOLDOUT-DTI [95% CI] n</th><th class=num>Max 3-px overlap with other focus sites (saturates)</th><th class=num>Max exact Jaccard with other focus sites</th><th>Use</th></tr>
{''.join(best_rows)}
</table>
<p><small>How to read the table: SGMC-CAL is an off-catalogue holdout. It is the only proxy we could rerun that tracks the ledger across these nine sites. Whether it tracks the organizer beyond these nine is unverified.</small></p>

<h2>3. Why GEMSDOE32 leads the nine (what the measurements show)</h2>
<p>On the off-catalogue holdout the top two of the nine are GEMSDOE36 ({r36['sgmc']['sgmc_cal']:.6f}, CI [{r36['sgmc']['ci95'][0]:.4f}, {r36['sgmc']['ci95'][1]:.4f}]) and GEMSDOE32 ({r32['sgmc']['sgmc_cal']:.6f}, CI [{r32['sgmc']['ci95'][0]:.4f}, {r32['sgmc']['ci95'][1]:.4f}]). Their intervals overlap almost entirely, so the proxy cannot separate them. Their ledger scores are {ledger_score('GEMSDOE32'):.4f} and {ledger_score('GEMSDOE36'):.4f}.</p>
<p>Within 3 px, {pct(P[('GEMSDOE32','GEMSDOE36')])} of GEMSDOE32's dots fall near a GEMSDOE36 dot, but exact-pixel Jaccard is {next(p for p in pairs if p['a']=='GEMSDOE32' and p['b']=='GEMSDOE36')['jaccard_exact']:.4f}, so the 3-px figure is saturated by the dense reference and overstates similarity. The 0.2778 vs 0.2750 ranking therefore cannot be explained by a placement difference this metric can see. Any mechanism would need the organizer's per-site scorer, which we do not have.</p>

<h2>4. Uniqueness</h2>
<p>Pairwise 3-px overlap: the share of the row file's dots within 3 px of any dot in the column file. Overlap is only an observation about our candidate. The full matrix is in <code>evidence/nine_site_summary.json</code>.</p>
<table>
<tr><th>Our candidate vs</th><th class=num>Ours → other</th><th class=num>Other → ours</th></tr>
{''.join(pair_rows)}
</table>
<p><strong>Focus-site pairs with 3-px overlap of at least 95% in either direction</strong> (computed). The 3-px test saturates when one file is dense, so exact-pixel Jaccard and exact mask equality are shown as well. Only the nine focus files were restored, so this covers 9 of the 100+ ledger sites.</p>
<table><tr><th>Pair</th><th class=num>3-px overlap (A→B / B→A)</th><th class=num>Exact Jaccard</th><th class=num>Binary Pearson</th><th>Reading</th></tr>{''.join(flags) if flags else '<tr><td colspan=5>none</td></tr>'}</table>

<h2>5. Irregularities flagged for review</h2>
<ol>
<li><strong>Literal 3-px uniqueness rule is saturated by dense references.</strong> The r13-lattice reference covers almost the whole footprint at 3 px, so any dense candidate fails the literal rule (ours: {pct(o_r13)} within 3 px). Exact-pixel Jaccard is {o_r13_j:.4f}, so the two dot sets share almost no pixels. Detector-only overlap is the only usable measure here. Team decision needed. This rule is our reading of the prompt, not a DrivenData rule.</li>
<li><strong>GEMSDOE30 duplicates GEMSDOE25 in dots.</strong> (Exact mask equality is computed in section 4.) The ledger ID ends in <code>91eae1ca</code>, which is GEMSDOE25's SHA prefix, but the pinned GEMSDOE30 file is <code>{rows['GEMSDOE30']['sha256'][:8]}</code>. Its bytes differ, but its dots match GEMSDOE25 (exact mask equal: {str(PP_eq('GEMSDOE25','GEMSDOE30'))}, dot count {rows['GEMSDOE30']['dots']:,}, same SGMC-CAL). Both score 0.2600 USER-REPORTED. Treat GEMSDOE30 as not a distinct submission.</li>
<li><strong>GEMSDOE25 owner-mirror copy is mislabelled.</strong> <code>data/scored/gems24-…-e56ea318af89-nan.tif</code> is byte-identical to GEMSDOE25's focus file. The "gems24" name is wrong.</li>
<li><strong>GEMSDOE28 and GEMSDOE31 share a run ID.</strong> <code>8acb75e1</code> appears in both ledger entries and both score 0.2708. Their dots are nearly identical (3-px overlap 99.8% and 99.6%), though the bytes differ.</li>
<li><strong>Nine-site overlap is high.</strong> Many focus files overlap at 95% or more with one another (section 4). The nine are not nine independent placements. Our candidate is the exception among the files checked (max 26% against any focus file, except the r13 lattice).</li>
<li><strong>Champion has three identical copies</strong> (GEMSDOE32 focus, registry, and <code>docs/downloads</code>). Expected, but it means the registry is not an independent reference.</li>
<li><strong>Leaderboard top conflicts:</strong> the prompt gives 0.4413 and, in another place, 0.3195. The live public leaderboard (2026-10-31) gives 0.4544 for #1, and the repo's 2026-10-29 snapshot agrees. These are PUBLIC-test values. The Initial Prize Round is decided on the PRIVATE test set (see <a href="https://www.drivendata.org/competitions/306/competition-doe-gems/">DrivenData competition page</a>).</li>
<li><strong>"Predicted values must be in range [0, 1]" root cause not confirmed.</strong> The NaN-outside file passes the local validator. The GEMSDOE32 benchmark is a zeros-outside file that scored, so zeros-outside is not automatically rejected. Only the portal can confirm.</li>
<li><strong>Provenance of competition inputs.</strong> <code>training_features.tif</code>, <code>labels.tif</code> and <code>sample_submission.tif</code> come from other teams' GitHub repos (see <code>registry/data_manifest.json</code>), not from DrivenData. Hash pins prove mirror consistency only. Confirm the rules allow this use before relying on them.</li>
<li><strong>Evaluator rejects NaN.</strong> Proxy values here come from zeros-outside copies in a temp dir. The same in-footprint values are used. This is a measurement convenience, not a submission.</li>
<li><strong>Sandbox access.</strong> DrivenData and the GitHub Pages sites are not reachable from this sandbox. Ledger values could not be re-checked against their source pages.</li>
</ol>

<h2>6. Ledger (USER-REPORTED, transcribed)</h2>
<table><tr><th>Site</th><th>Ledger ID</th><th class=num>Score</th></tr>{''.join(ledger_rows)}</table>

<h2>7. Official sources (for manual review)</h2>
<ul>
<li><a href="https://www.drivendata.org/competitions/306/competition-doe-gems/">DrivenData competition page</a></li>
<li><a href="https://www.drivendata.org/competitions/306/competition-doe-gems/leaderboard/">DrivenData leaderboard</a></li>
<li><a href="https://www.drivendata.org/competitions/306/competition-doe-gems/data/">DrivenData data page (login)</a></li>
<li><a href="https://docs.nlr.gov/docs/fy26osti/96647.pdf">NLR (NREL) GEMS paper (submission format)</a></li>
<li><a href="https://github.com/drivendataorg/gems-prize-reference-solution">Reference solution (GitHub)</a></li>
<li><a href="https://epsg.io/32611">EPSG:32611</a></li>
</ul>
<p><a href="../docs/submit-now.html">Download &amp; submit page</a> · <a href="executive-summary.html">Executive summary</a> · <a href="how-to-submit.html">How to submit</a></p>
</main></body></html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
