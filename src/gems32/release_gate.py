"""Fail-closed parallel-run gates. These never allocate competition submission slots."""
from __future__ import annotations

import re

import numpy as np
from scipy.ndimage import distance_transform_edt
from scipy.stats import spearmanr


def compare_registry(surface, dots, footprint, registry, *, stage="final", inventory_complete=False):
    """Exact ranks and directional <=3px support overlap, without exemptions.

    At the surface stage ``dots`` is a preregistered preview-support mask; at the
    final stage it is the actual placed-dot mask. The caller must prove that the
    inventory is complete for its stated scope; omission fails closed. This
    function cannot by itself prove that remote/private repositories were scanned.
    """
    if stage not in {"surface", "final"}:
        raise ValueError("stage must be surface or final")
    surface = np.asarray(surface)
    foot_raw = np.asarray(footprint)
    if not np.isfinite(foot_raw).all() or not np.isin(foot_raw, (0, 1)).all():
        raise ValueError("footprint must already be finite and binary")
    footprint = foot_raw.astype(bool, copy=False)
    if dots is None:
        raise ValueError("a pre-placement preview support or final dots mask is required")
    raw_dots = np.asarray(dots)
    if not np.isfinite(raw_dots).all() or not np.isin(raw_dots, (0, 1)).all():
        raise ValueError("candidate support must already be finite and binary")
    dots = raw_dots.astype(bool, copy=False)
    if surface.shape != footprint.shape or dots.shape != footprint.shape:
        raise ValueError("surface/dots/footprint shape mismatch")
    if not footprint.any() or not np.isfinite(surface[footprint]).all():
        raise ValueError("empty footprint or nonfinite candidate surface")
    if (dots & ~footprint).any():
        raise ValueError("candidate support extends outside the footprint")
    rows = []
    for name, (other_surface, other_dots) in registry.items():
        other_surface, other_raw = np.asarray(other_surface), np.asarray(other_dots)
        if other_surface.shape != footprint.shape or other_raw.shape != footprint.shape:
            raise ValueError(f"registry shape mismatch: {name}")
        if not np.isfinite(other_raw[footprint]).all() or not np.isin(other_raw[footprint], (0, 1)).all():
            raise ValueError(f"registry support must be finite and binary inside footprint: {name}")
        other_dots = (other_raw == 1) & footprint
        rho = None
        if np.isfinite(other_surface[footprint]).all():
            x, y = surface[footprint], other_surface[footprint]
            if np.ptp(x) > 0 and np.ptp(y) > 0:
                rho = float(spearmanr(x, y).statistic)
        overlap = None
        dot_rho = None
        if dots.any() and other_dots.any():
            overlap = float((distance_transform_edt(~other_dots)[dots] <= 3).mean())
            # Exact Spearman for binary fields equals the Pearson phi coefficient.
            n, a, b = int(footprint.sum()), int(dots.sum()), int(other_dots.sum())
            both = int((dots & other_dots).sum())
            den = float(a * (n - a) * b * (n - b)) ** 0.5
            if den:
                dot_rho = float((n * both - a * b) / den)
        duplicate = ((rho is not None and rho > .90) or
                     (dot_rho is not None and dot_rho > .90) or
                     (overlap is not None and overlap > .70))
        rows.append(dict(registry=name, spearman_surface=rho, spearman_support=dot_rho,
                         within_3px_fraction=overlap, duplicate=duplicate,
                         measurable=rho is not None and dot_rho is not None and overlap is not None))
    passed = (inventory_complete is True and bool(rows) and bool(dots.any())
              and all(r['measurable'] and not r['duplicate'] for r in rows))
    return dict(stage=stage, rule="literal rho>0.90 OR directional overlap>0.70; no density exemptions",
                inventory_complete=inventory_complete is True,
                comparisons=rows, passed=passed, stop=not passed)


REQUIRED_VALIDATOR_CHECKS = frozenset({
    "exact_reference_grid_match", "single_band", "dtype_float32", "dimensions_3730x3292",
    "crs_epsg_32611", "in_footprint_all_finite", "in_footprint_zero_nan",
    "in_footprint_range_0_1", "outside_footprint_compliant", "zero_on_catalogue_leakage",
})


def _valid_holdout(result):
    """Fail closed unless an independent fold-local replay has been verified."""
    if not isinstance(result, dict):
        return False
    try:
        ci = result.get("ci95_cluster_bootstrap", result.get("ci95", []))
        dti = result.get("pooled_dti", result.get("dti"))
        n = result["n_withheld_positives"]
        replay_hash = result.get("independent_replay_sha256", "")
        return bool(
            result.get("score_label") == "HOLDOUT-DTI"
            and isinstance(result.get("evaluator_version"), str)
            and result["evaluator_version"].strip()
            and result.get("catalogue_feature_provenance_verified") is True
            and isinstance(replay_hash, str) and re.fullmatch(r"[0-9a-f]{64}", replay_hash)
            and isinstance(n, int) and not isinstance(n, bool) and n > 0
            and len(ci) == 2 and all(_real(v, 0, 1) for v in (dti, *ci))
            and ci[0] <= dti <= ci[1]
        )
    except (KeyError, TypeError, ValueError):
        return False


def _real(value, lo, hi):
    return (not isinstance(value, (bool, np.bool_)) and isinstance(value, (float, int, np.floating, np.integer))
            and np.isfinite(value) and lo <= value <= hi)


def _gate_ok(result, stage):
    """Recheck raw measurements, not just a caller-supplied ``passed`` flag."""
    if not isinstance(result, dict) or result.get("stage") != stage:
        return False
    rows = result.get("comparisons")
    if not (result.get("inventory_complete") is True and result.get("passed") is True
            and result.get("stop") is False and isinstance(rows, list) and rows):
        return False
    names = []
    for row in rows:
        if not isinstance(row, dict):
            return False
        name = row.get("registry")
        if not isinstance(name, str) or not name.strip():
            return False
        names.append(name)
        if not (row.get("measurable") is True and row.get("duplicate") is False
                and _real(row.get("spearman_surface"), -1, .90)
                and _real(row.get("spearman_support"), -1, .90)
                and _real(row.get("within_3px_fraction"), 0, .70)):
            return False
    return len(set(names)) == len(names)


def promotion_decision(*, lane, surface_check, final_check, canary_aucs,
                       holdout, incumbent, same_evaluation, validator,
                       paired_delta_ci95=None, expected_features=None):
    """Return a recommendation only, never select a real slot.

    Missing registry coverage, a missing/symmetric-AUC-failed feature canary, unverified fold-local
    replay, differing evaluation-design hashes, an unauthenticated sample, or a paired CI touching zero blocks it.
    Even a promote result requires a separate selector and organizer quota check.
    """
    try:
        paired_win = bool(paired_delta_ci95 is not None
                          and len(paired_delta_ci95) == 2
                          and all(_real(v, 0, 1) for v in paired_delta_ci95)
                          and 0 < paired_delta_ci95[0] <= paired_delta_ci95[1] <= 1)
        feature_set = set(expected_features or [])
        canary_ok = (isinstance(canary_aucs, dict) and bool(feature_set)
                     and set(canary_aucs) == feature_set
                     and all(_real(a, .10, .90) for a in canary_aucs.values()))
    except (TypeError, ValueError):
        paired_win = canary_ok = False
    holdout_ok = _valid_holdout(holdout) and _valid_holdout(incumbent)
    checks = validator.get("checks", {}) if isinstance(validator, dict) else {}
    format_ok = (isinstance(checks, dict) and REQUIRED_VALIDATOR_CHECKS.issubset(checks)
                 and all(v is True for v in checks.values())
                 and validator.get("all_checks_passed") is True
                 and validator.get("organizer_template_authenticated") is True
                 and validator.get("official_outside_bounds_null_or_nan") is True
                 and validator.get("official_submission_format_compatible") is True)
    gates = dict(
        lane=isinstance(lane, str) and bool(lane.strip()),
        surface=_gate_ok(surface_check, 'surface'), final=_gate_ok(final_check, 'final'),
        same_registry=bool(_gate_ok(surface_check, 'surface') and _gate_ok(final_check, 'final')
                           and {r['registry'] for r in surface_check['comparisons']}
                           == {r['registry'] for r in final_check['comparisons']}),
        canaries=bool(canary_ok),
        holdout=bool(same_evaluation is True and holdout_ok
                     and holdout['evaluator_version'] == incumbent['evaluator_version']
                     and holdout['n_withheld_positives'] == incumbent['n_withheld_positives']
                     and isinstance(holdout.get('evaluation_design_sha256'), str)
                     and re.fullmatch(r'[0-9a-f]{64}', holdout['evaluation_design_sha256']) is not None
                     and holdout['evaluation_design_sha256'] == incumbent.get('evaluation_design_sha256')
                     and holdout.get('pooled_dti',holdout.get('dti')) > incumbent.get('pooled_dti',incumbent.get('dti'))),
        paired_improvement=paired_win,
        format=bool(format_ok),
    )
    return dict(gates=gates, verdict='promote' if all(gates.values()) else 'negative',
                selector_required=True, slot_used=False)
