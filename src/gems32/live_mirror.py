"""Live-mirror holdout instrument (LM) -- a spatially blocked evaluation built to *reproduce the
sign* of the public leaderboard, not the sign of the visible catalogue.

Why this exists
---------------
Every locally available truth raster in this competition is derived from the published catalogue,
and the organisers **mask catalogue pixels out of scoring**.  A holdout whose truth *is* the
catalogue therefore rewards exactly the mass the live scorer throws away.  This repository had
already measured that inversion (see `evidence/bo_surrogate_summary.json`), but it had never built
an instrument that gets the sign right, and it had never validated one against the live record.

What LM does
------------
For each of the four spatially blocked quadrants it evaluates the **exact official
distance-weighted Tversky index** against a truth set that is, by construction, *off catalogue*:
the USGS State Geologic Map Compilation (SGMC) fault pixels that lie more than 300 m from every
catalogue pixel inside the held-out domain.  Because the truth excludes the catalogue, mass spent
on the catalogue and its flank is charged ``alpha`` per dot and earns nothing -- which is precisely
what the live scorer does to it.

Validation target (three *known* live orderings, all owner-reported):
    0.2708 (D2.8 minus the 3,891 dots at d_catalogue = 1 px)  >  0.2600 (D2.8)
    0.2600 (D2.8)                                            >  0.2477 (D1.5)
    0.2477 (D1.5)                                            >  0.2449 (T-v2 on D1.5)
An instrument that reproduces all three is usable for ranking *emission rules*; one that does not
is not, whatever its other statistics say.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import binary_dilation, binary_erosion, distance_transform_edt

from .metric import ALPHA, BETA, EPS, kernel

FOLD_NAMES = ("NW", "NE", "SW", "SE")
FOLDS = (0, 1, 2, 3)
COLLAR_PX = 15       # 1.5 km spatial buffer between the visible catalogue and the test quadrant
DOMAIN_ERODE = 12    # 1.2 km boundary erosion of the test quadrant
CAT_FLANK_PX = 3     # the official kernel radius; SGMC truth is taken strictly beyond it


@dataclass
class LiveMirrorCell:
    key: str
    fold: int
    bbox: tuple[slice, slice]
    domain: np.ndarray
    truth: np.ndarray
    truth_coords: tuple[np.ndarray, np.ndarray]
    n_truth: int


@dataclass
class LiveMirrorContext:
    foot: np.ndarray
    labels: np.ndarray
    sgmc_off: np.ndarray
    quad: np.ndarray
    cells: list[LiveMirrorCell]


def _quadrant_ids(footprint: np.ndarray) -> np.ndarray:
    footprint = np.asarray(footprint, bool)
    yy, xx = np.nonzero(footprint)
    ym, xm = int(np.median(yy)), int(np.median(xx))
    H, W = footprint.shape
    gy, gx = np.ogrid[:H, :W]
    q = np.full((H, W), -1, np.int8)
    q[(gy < ym) & (gx < xm) & footprint] = 0
    q[(gy < ym) & (gx >= xm) & footprint] = 1
    q[(gy >= ym) & (gx < xm) & footprint] = 2
    q[(gy >= ym) & (gx >= xm) & footprint] = 3
    return q


def load_live_mirror_context(ddir, foot: np.ndarray, labels: np.ndarray) -> LiveMirrorContext:
    """Build the four spatially blocked off-catalogue truth cells."""
    import rasterio

    with rasterio.open(ddir / "external" / "derived_sgmc_faults_100m_u8.tif") as ds:
        sgmc = ds.read(1) > 0
    sgmc_off = sgmc & foot & ~labels & ~binary_dilation(labels, iterations=CAT_FLANK_PX)

    quad = _quadrant_ids(foot)
    cells: list[LiveMirrorCell] = []
    for fold in FOLDS:
        q = quad == fold
        rows = np.flatnonzero(q.any(axis=1))
        cols = np.flatnonzero(q.any(axis=0))
        # pad the bbox by 6 px so the 3-px kernel matches the full-grid distance transform exactly
        r0 = max(0, int(rows[0]) - 6)
        r1 = min(foot.shape[0], int(rows[-1]) + 7)
        c0 = max(0, int(cols[0]) - 6)
        c1 = min(foot.shape[1], int(cols[-1]) + 7)
        sl = (slice(r0, r1), slice(c0, c1))
        domain = binary_erosion(q, iterations=DOMAIN_ERODE)
        truth = (sgmc_off & domain)[sl]
        tc = np.nonzero(truth)
        cells.append(LiveMirrorCell(key=f"fold{FOLD_NAMES[fold]}", fold=fold, bbox=sl,
                                    domain=domain[sl], truth=truth, truth_coords=tc,
                                    n_truth=int(tc[0].size)))
    return LiveMirrorContext(foot=foot, labels=labels, sgmc_off=sgmc_off, quad=quad, cells=cells)


def official_dti(P: np.ndarray, G: np.ndarray) -> dict:
    """The exact official distance-weighted Tversky index between a prediction and a truth raster."""
    P = np.asarray(P, bool)
    G = np.asarray(G, bool)
    n_p = int(P.sum())
    n_g = int(G.sum())
    if n_p == 0 or n_g == 0:
        return {"dti": 0.0, "tp_w": 0.0, "tp_p": 0.0, "tp_g": 0.0, "n_p": n_p, "n_g": n_g}
    dp = distance_transform_edt(~P)
    dg = distance_transform_edt(~G)
    tp_p = float(kernel(dp[G]).sum())
    tp_g = float(kernel(dg[P]).sum())
    tp_w = 0.5 * (tp_p + tp_g)
    denom = ALPHA * n_p + BETA * n_g + BETA * (tp_g - tp_p) + EPS
    return {"dti": float(tp_w / denom), "tp_w": tp_w, "tp_p": tp_p, "tp_g": tp_g,
            "n_p": n_p, "n_g": n_g}


def evaluate_live_mirror(mask: np.ndarray, ctx: LiveMirrorContext, name: str = "candidate",
                         flank_charge_px: int | None = None,
                         calibrate_prevalence: bool = False,
                         g_lb_total: float = 12691.0) -> dict:
    """Score `mask` under LM.

    `flank_charge_px=B` additionally *deletes* every dot within B px of the catalogue before
    scoring, which is the "catalogue-flank exclusion" policy.  With ``None`` the mask is scored as
    given, so on-catalogue mass is charged alpha and earns nothing (the live behaviour).

    `calibrate_prevalence=True` replaces each fold's raw SGMC truth count by the live-calibrated
    hidden-truth prevalence ``g_lb_total`` scaled by the fold's share of the footprint.  Without it
    LM inherits the 4.94x SGMC density inflation (IR-32-03) and over-rewards spraying mass.
    """
    mask = np.asarray(mask, bool) & ctx.foot
    n_raw = int(mask.sum())
    if flank_charge_px is not None:
        d_cat = distance_transform_edt(~ctx.labels)
        mask = mask & (d_cat > flank_charge_px)
    n_emit = int(mask.sum())

    foot_px = float(ctx.foot.sum())
    per_fold: dict[str, float] = {}
    per_fold_cal: dict[str, float] = {}
    details: dict[str, dict] = {}
    for cell in ctx.cells:
        sl = cell.bbox
        p = mask[sl] & cell.domain
        g = cell.truth
        r = official_dti(p, g)
        per_fold[cell.key] = r["dti"]
        details[cell.key] = r
        if calibrate_prevalence and r["n_g"] > 0:
            g_cal = g_lb_total * (float(cell.domain.sum()) / foot_px)
            denom_cal = ALPHA * r["n_p"] + BETA * g_cal + BETA * (r["tp_g"] - r["tp_p"]) + EPS
            per_fold_cal[cell.key] = float(r["tp_w"] / denom_cal)
        else:
            per_fold_cal[cell.key] = r["dti"]
    vals = np.array(list(per_fold.values()), dtype=np.float64)
    vals_cal = np.array(list(per_fold_cal.values()), dtype=np.float64)
    return {
        "candidate_id": name,
        "lm_mean": float(vals.mean()),
        "lm_std": float(vals.std()),
        "lm_per_fold": per_fold,
        "lm_min_fold": float(vals.min()),
        "lm_folds_positive": int((vals > 0).sum()),
        "lm_calibrated_mean": float(vals_cal.mean()),
        "lm_calibrated_std": float(vals_cal.std()),
        "lm_calibrated_per_fold": per_fold_cal,
        "lm_calibrated_min_fold": float(vals_cal.min()),
        "emitted_pixels": n_emit,
        "emitted_pixels_before_flank_policy": n_raw,
        "on_catalogue_pixels": int((mask & ctx.labels).sum()),
        "fold_detail": details,
    }


# --------------------------------------------------------------------------------------------
# Instrument validation against the live record
# --------------------------------------------------------------------------------------------

# (label, path relative to data_dir, owner-reported live DTI)
LIVE_REFERENCE_CHAIN = [
    ("D2.8", "scored/gems24-h25-1-dotted-h19-5-d2-8-20261002-e56ea318af89-nan.tif", 0.2600),
    ("H27-4-R1-SOLO", "scored/gems28-h27-4-r1-solo-d2-8-20261003-8acb75e1f2cc-nan.tif", 0.2708),
    ("D1.5", "scored/gems24-h25-1-dotted-h19-5-d1-5-20261002-989f59505db1-nan.tif", 0.2477),
    ("T-V2-ON-D1.5", "scored/gems27-topo-gap-closure-t-v2-on-d1-5-20261002-5512495c6bd1-nan.tif", 0.2449),
    ("H19-5", "scored/gems19-h19-5-powerlaw-budget-multiline-corroborated-20260930-e27054cf-nan.tif", 0.1922),
    ("H16-1", "scored/gems16-h16-1-topo-geophys-baseline-ridges-20260930-df20f65e-nan.tif", 0.1911),
    ("LATTICE-S5", "scored/13gems_20261001_r13-lattice-s5_v2_nan-outside.tif", 0.0904),
    ("PLACEHOLDER", "scored/gemsdoe9-PLACEHOLDER-2314b599.tif", 0.0445),
]

# Orderings that are *known* from the live record.  Each is a strict inequality on the
# owner-reported public score.  An instrument is only allowed to rank emission rules if it
# reproduces all of them.
LIVE_ORDERINGS = [
    ("H27-4-R1-SOLO", "D2.8", 0.2708, 0.2600),
    ("D2.8", "D1.5", 0.2600, 0.2477),
    ("D1.5", "T-V2-ON-D1.5", 0.2477, 0.2449),
    ("H19-5", "H16-1", 0.1922, 0.1911),
    ("H16-1", "LATTICE-S5", 0.1911, 0.0904),
    ("LATTICE-S5", "PLACEHOLDER", 0.0904, 0.0445),
]


def validate_live_mirror(ddir, ctx: LiveMirrorContext) -> dict:
    """Score every live-scored reference under LM and check it reproduces the live orderings."""
    from .holdout import read_binary

    scores: dict[str, dict] = {}
    for label, rel, lb in LIVE_REFERENCE_CHAIN:
        p = ddir / rel
        if not p.exists():
            continue
        m = read_binary(p)
        r = evaluate_live_mirror(m, ctx, label)
        r["leaderboard_dti"] = lb
        r_cal = evaluate_live_mirror(m, ctx, label, calibrate_prevalence=True)
        r["lm_calibrated_mean"] = r_cal["lm_calibrated_mean"]
        r["lm_calibrated_per_fold"] = r_cal["lm_calibrated_per_fold"]
        scores[label] = r

    checks = []
    for hi, lo, lb_hi, lb_lo in LIVE_ORDERINGS:
        if hi not in scores or lo not in scores:
            continue
        got_hi = scores[hi]["lm_mean"]
        got_lo = scores[lo]["lm_mean"]
        c_hi = scores[hi]["lm_calibrated_mean"]
        c_lo = scores[lo]["lm_calibrated_mean"]
        checks.append({
            "ordering": f"{hi} > {lo}",
            "live": f"{lb_hi:.4f} > {lb_lo:.4f}",
            "lm": f"{got_hi:.6f} vs {got_lo:.6f}",
            "reproduced": bool(got_hi > got_lo),
            "lm_margin": float(got_hi - got_lo),
            "lm_calibrated": f"{c_hi:.6f} vs {c_lo:.6f}",
            "reproduced_calibrated": bool(c_hi > c_lo),
            "lm_calibrated_margin": float(c_hi - c_lo),
        })
    n_ok = sum(1 for c in checks if c["reproduced"])
    n_ok_cal = sum(1 for c in checks if c["reproduced_calibrated"])
    return {
        "instrument": "LM: spatially blocked official DTI against SGMC off-catalogue truth",
        "n_references_scored": len(scores),
        "n_orderings_checked": len(checks),
        "n_orderings_reproduced": n_ok,
        "all_reproduced": bool(n_ok == len(checks) and len(checks) > 0),
        "n_orderings_reproduced_calibrated": n_ok_cal,
        "all_reproduced_calibrated": bool(n_ok_cal == len(checks) and len(checks) > 0),
        "orderings": checks,
        "scores": {k: {"lm_mean": v["lm_mean"], "lm_per_fold": v["lm_per_fold"],
                       "lm_calibrated_mean": v["lm_calibrated_mean"],
                       "lm_calibrated_per_fold": v["lm_calibrated_per_fold"],
                       "emitted_pixels": v["emitted_pixels"],
                       "on_catalogue_pixels": v["on_catalogue_pixels"],
                       "leaderboard_dti": v["leaderboard_dti"]} for k, v in scores.items()},
    }
