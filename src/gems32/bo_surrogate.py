"""Bayesian Optimization (Gaussian Process) Surrogate & Holdout-to-Leaderboard Drift Model.

Implements:
1. 10D continuous design vector encoding x in R^10 for every historical and new candidate.
2. Matern-5/2 Gaussian Process surrogate over holdout DTI (`catalogue_hidden_mean` and
   `drift_corrected_holdout_mean`), computing posterior (mu, sigma), Expected Improvement (EI),
   Probability of Improvement (PI), and 95% Upper Confidence Bound (UCB).
3. Holdout-to-Leaderboard Co-Kriging / Drift Correction model calibrated on the 9 non-leaking
   scored DrivenData submissions (and explicitly diagnosing the 2 retrospectively halo-leaked
   GEMSDOE10 rasters under IR-32-RETROSPECTIVE-HALO-LEAK).
4. Strict 3-slot/week submission budget gate: a candidate is eligible for a weekly submission slot
   if and only if it strictly beats the D2.8 incumbent across all three holdout metrics
   (catalogue_hidden_mean, sgmc_prevalence_calibrated_dti, drift_corrected_holdout_mean) with zero
   on-catalogue leakage.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.stats import norm, pearsonr, spearmanr
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel
from sklearn.preprocessing import StandardScaler

FEATURE_NAMES: tuple[str, ...] = (
    "n_dots_norm",
    "r_min_px_norm",
    "off_catalogue_purity",
    "corrob_multiline_weight",
    "w_h32a_dip_step",
    "w_h32b_transtensional_swarm",
    "w_h32c_mt_claycap",
    "w_lidar_3dep",
    "prune_fraction",
    "aug_fraction",
)


@dataclass
class CandidateDesign:
    candidate_id: str
    family: str
    submitted_to_lb: bool
    leaderboard_dti: float | None
    retrospective_halo_leakage: bool
    design_vector: dict[str, float]
    notes: str


def analytical_expected_improvement(
    mu: np.ndarray,
    sigma: np.ndarray,
    best_f: float,
    xi: float = 0.0001,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute analytical Expected Improvement (EI) and Probability of Improvement (PI)."""
    sig = np.maximum(sigma, 1e-9)
    imp = mu - best_f - xi
    z = imp / sig
    ei = imp * norm.cdf(z) + sig * norm.pdf(z)
    ei = np.where(sigma <= 1e-9, np.maximum(imp, 0.0), ei)
    pi = norm.cdf(z)
    return ei.astype(np.float64), pi.astype(np.float64)


def fit_gp_surrogate_and_rank(records: list[dict]) -> dict:
    """Fit Matern-5/2 GP surrogate on all non-leaking holdout evaluations and compute EI/UCB + LB drift."""
    clean_indices = [i for i, r in enumerate(records) if not r.get("retrospective_halo_leakage", False)]
    X_all = np.array([[r["design_vector"][k] for k in FEATURE_NAMES] for r in records], dtype=np.float64)
    X_clean = X_all[clean_indices]

    y_cat_clean = np.array([records[i]["catalogue_hidden_mean"] for i in clean_indices], dtype=np.float64)
    y_drf_clean = np.array([records[i]["drift_corrected_holdout_mean"] for i in clean_indices], dtype=np.float64)
    y_sgmc_clean = np.array([records[i]["sgmc_prevalence_calibrated_dti"] for i in clean_indices], dtype=np.float64)

    scaler = StandardScaler()
    X_clean_s = scaler.fit_transform(X_clean)
    X_all_s = scaler.transform(X_all)

    kernel_cat = ConstantKernel(1.0, (1e-3, 1e3)) * Matern(length_scale=1.5, length_scale_bounds=(0.15, 25.0), nu=2.5) + WhiteKernel(
        noise_level=1e-5, noise_level_bounds=(1e-12, 1e-1)
    )
    gp_cat = GaussianProcessRegressor(kernel=kernel_cat, alpha=1e-5, normalize_y=True, n_restarts_optimizer=8, random_state=32)
    gp_cat.fit(X_clean_s, y_cat_clean)

    kernel_drf = ConstantKernel(1.0, (1e-3, 1e3)) * Matern(length_scale=1.5, length_scale_bounds=(0.15, 25.0), nu=2.5) + WhiteKernel(
        noise_level=1e-5, noise_level_bounds=(1e-12, 1e-1)
    )
    gp_drf = GaussianProcessRegressor(kernel=kernel_drf, alpha=1e-5, normalize_y=True, n_restarts_optimizer=8, random_state=32)
    gp_drf.fit(X_clean_s, y_drf_clean)

    # Identify the historical non-leaking incumbent (D2.8 = 0.2600 LB)
    d28_rec = next(r for r in records if r["candidate_id"] == "D2.8-Poisson300m-Ref")
    best_hist_cat = float(d28_rec["catalogue_hidden_mean"])
    best_hist_drf = float(d28_rec["drift_corrected_holdout_mean"])
    best_hist_sgmc = float(d28_rec["sgmc_prevalence_calibrated_dti"])

    # Leave-one-out / predictive posterior for each candidate (for new candidates, condition on historical clean set
    # so EI reflects genuine prospective acquisition utility before observing the candidate, plus full-posterior UCB)
    hist_clean_indices = [
        i for i, r in enumerate(records)
        if not r.get("retrospective_halo_leakage", False) and r.get("is_historical", False)
    ]
    X_hist_s = X_all_s[hist_clean_indices]
    y_hist_cat = np.array([records[i]["catalogue_hidden_mean"] for i in hist_clean_indices], dtype=np.float64)
    y_hist_drf = np.array([records[i]["drift_corrected_holdout_mean"] for i in hist_clean_indices], dtype=np.float64)

    gp_prospective_drf = GaussianProcessRegressor(
        kernel=kernel_drf, alpha=2e-4, normalize_y=True, n_restarts_optimizer=6, random_state=32
    )
    gp_prospective_drf.fit(X_hist_s, y_hist_drf)

    # Fit Holdout-to-Leaderboard Co-Kriging / Drift Calibration on the 9 non-leaking scored submissions
    scored_clean_idx = [
        i for i, r in enumerate(records)
        if (r.get("leaderboard_dti") is not None) and (not r.get("retrospective_halo_leakage", False))
    ]
    ho_drf_scored = np.array([records[i]["drift_corrected_holdout_mean"] for i in scored_clean_idx], dtype=np.float64)
    ho_cat_scored = np.array([records[i]["catalogue_hidden_mean"] for i in scored_clean_idx], dtype=np.float64)
    ho_sgmc_scored = np.array([records[i]["sgmc_prevalence_calibrated_dti"] for i in scored_clean_idx], dtype=np.float64)
    lb_scored = np.array([records[i]["leaderboard_dti"] for i in scored_clean_idx], dtype=np.float64)

    # Linear + GP residual co-kriging from (catalogue_hidden_mean, sgmc_prevalence_calibrated_dti, drift_corrected_holdout_mean) to LB
    A_design = np.column_stack([np.ones_like(ho_drf_scored), ho_cat_scored, ho_sgmc_scored, ho_drf_scored])
    # Ridge-regularized weights
    reg = np.diag([0.0, 1e-4, 1e-4, 1e-4])
    beta_lb = np.linalg.solve(A_design.T @ A_design + reg, A_design.T @ lb_scored)
    lb_lin_pred_scored = A_design @ beta_lb
    lb_residuals = lb_scored - lb_lin_pred_scored

    gp_lb_res = GaussianProcessRegressor(
        kernel=ConstantKernel(0.01, (1e-8, 10.0)) * Matern(length_scale=1.5, nu=2.5)
        + WhiteKernel(1e-4, noise_level_bounds=(1e-12, 1e-1)),
        alpha=1e-4,
        normalize_y=False,
        random_state=32,
    )
    gp_lb_res.fit(X_all_s[scored_clean_idx], lb_residuals)

    # Compute GP posterior across all records
    mu_cat_all, std_cat_all = gp_cat.predict(X_all_s, return_std=True)
    mu_drf_all, std_drf_all = gp_drf.predict(X_all_s, return_std=True)
    mu_prosp_drf, std_prosp_drf = gp_prospective_drf.predict(X_all_s, return_std=True)

    # Combine empirical spatial quadrant SE with GP epistemic uncertainty
    quad_se_drf = np.array([r["drift_corrected_holdout_std"] / math.sqrt(4.0) for r in records], dtype=np.float64)
    eff_sigma_drf = np.hypot(std_drf_all, 0.25 * quad_se_drf)

    ei_drf, pi_drf = analytical_expected_improvement(
        np.array([r["drift_corrected_holdout_mean"] for r in records], dtype=np.float64),
        eff_sigma_drf,
        best_f=best_hist_drf,
        xi=0.0001,
    )
    quad_se_cat = np.array([r["catalogue_hidden_std"] / math.sqrt(4.0) for r in records], dtype=np.float64)
    eff_sigma_cat = np.hypot(std_cat_all, 0.25 * quad_se_cat)
    ei_cat, pi_cat = analytical_expected_improvement(
        np.array([r["catalogue_hidden_mean"] for r in records], dtype=np.float64),
        eff_sigma_cat,
        best_f=best_hist_cat,
        xi=0.00005,
    )

    # Predict Leaderboard DTI for every record via Co-Kriging
    A_all = np.column_stack([
        np.ones(len(records)),
        np.array([r["catalogue_hidden_mean"] for r in records]),
        np.array([r["sgmc_prevalence_calibrated_dti"] for r in records]),
        np.array([r["drift_corrected_holdout_mean"] for r in records]),
    ])
    lb_res_mu, lb_res_std = gp_lb_res.predict(X_all_s, return_std=True)
    lb_pred_mu = A_all @ beta_lb + lb_res_mu
    lb_pred_std = np.hypot(lb_res_std, 0.0065)
    ei_lb, pi_lb = analytical_expected_improvement(lb_pred_mu, lb_pred_std, best_f=0.2600, xi=0.0002)

    for idx, r in enumerate(records):
        r["gp_posterior_cat_mean"] = round(float(mu_cat_all[idx]), 6)
        r["gp_posterior_cat_std"] = round(float(eff_sigma_cat[idx]), 6)
        r["gp_posterior_drift_mean"] = round(float(mu_drf_all[idx]), 6)
        r["gp_posterior_drift_std"] = round(float(eff_sigma_drf[idx]), 6)
        r["gp_prospective_drift_mean"] = round(float(mu_prosp_drf[idx]), 6)
        r["gp_prospective_drift_std"] = round(float(std_prosp_drf[idx]), 6)
        r["ei_catalogue_hidden"] = round(float(ei_cat[idx]), 6)
        r["pi_catalogue_hidden"] = round(float(pi_cat[idx]), 4)
        r["ei_drift_corrected"] = round(float(ei_drf[idx]), 6)
        r["pi_drift_corrected"] = round(float(pi_drf[idx]), 4)
        r["ucb95_drift_corrected"] = round(float(r["drift_corrected_holdout_mean"] + 1.96 * eff_sigma_drf[idx]), 6)
        r["predicted_leaderboard_dti"] = round(float(lb_pred_mu[idx]), 4)
        r["predicted_leaderboard_std"] = round(float(lb_pred_std[idx]), 4)
        r["ei_leaderboard_over_02600"] = round(float(ei_lb[idx]), 6)
        r["pi_leaderboard_over_02600"] = round(float(pi_lb[idx]), 4)

        beats_all_three = (
            (not r.get("retrospective_halo_leakage", False))
            and (not r.get("is_historical", False))
            and (r["on_catalogue_emitted_px"] == 0)
            and (r["catalogue_hidden_mean"] > best_hist_cat)
            and (r["sgmc_prevalence_calibrated_dti"] > best_hist_sgmc)
            and (r["drift_corrected_holdout_mean"] > best_hist_drf)
        )
        r["beats_incumbent_all_holdouts"] = bool(beats_all_three)

    # Allocate the 3 weekly submission slots among new candidates that beat D2.8 on all holdouts
    eligible_new = [r for r in records if r["beats_incumbent_all_holdouts"]]
    eligible_new.sort(key=lambda r: (r["ei_drift_corrected"] + 0.5 * r["ei_catalogue_hidden"]), reverse=True)
    slot_map = {}
    for rank_idx, r in enumerate(eligible_new[:3], start=1):
        slot_map[r["candidate_id"]] = f"SLOT_{rank_idx}_OF_3_ALLOCATED"
    for r in eligible_new[3:]:
        slot_map[r["candidate_id"]] = "RESERVE_VERIFIED_BEATS_D28"

    for r in records:
        cid = r["candidate_id"]
        if cid in slot_map:
            r["slot_decision"] = slot_map[cid]
        elif r.get("is_historical", False):
            r["slot_decision"] = "HISTORICAL_BASELINE"
        else:
            r["slot_decision"] = "REJECTED_BY_HOLDOUT_GATE"

    # Correlation diagnostics on historical submissions
    all_scored_idx = [i for i, r in enumerate(records) if r.get("leaderboard_dti") is not None]
    lb_all = np.array([records[i]["leaderboard_dti"] for i in all_scored_idx])
    cat_all = np.array([records[i]["catalogue_hidden_mean"] for i in all_scored_idx])
    sgmc_raw_all = np.array([records[i]["sgmc_off_catalogue_raw_dti"] for i in all_scored_idx])
    sgmc_cal_all = np.array([records[i]["sgmc_prevalence_calibrated_dti"] for i in all_scored_idx])
    drf_all = np.array([records[i]["drift_corrected_holdout_mean"] for i in all_scored_idx])

    diagnostics = {
        "incumbent_candidate_id": "D2.8-Poisson300m-Ref",
        "incumbent_leaderboard_dti": 0.2600,
        "incumbent_catalogue_hidden_mean": round(best_hist_cat, 6),
        "incumbent_sgmc_prevalence_calibrated_dti": round(best_hist_sgmc, 6),
        "incumbent_drift_corrected_holdout_mean": round(best_hist_drf, 6),
        "gp_cat_kernel_fitted": str(gp_cat.kernel_),
        "gp_drift_kernel_fitted": str(gp_drf.kernel_),
        "co_kriging_linear_weights": {
            "intercept": round(float(beta_lb[0]), 6),
            "w_catalogue_hidden": round(float(beta_lb[1]), 6),
            "w_sgmc_calibrated": round(float(beta_lb[2]), 6),
            "w_drift_corrected": round(float(beta_lb[3]), 6),
        },
        "correlations_all_11_scored": {
            "n": int(len(all_scored_idx)),
            "catalogue_hidden_spearman": round(float(spearmanr(cat_all, lb_all).statistic), 4),
            "catalogue_hidden_pearson": round(float(pearsonr(cat_all, lb_all).statistic), 4),
            "sgmc_raw_spearman": round(float(spearmanr(sgmc_raw_all, lb_all).statistic), 4),
            "sgmc_calibrated_spearman": round(float(spearmanr(sgmc_cal_all, lb_all).statistic), 4),
            "drift_corrected_spearman": round(float(spearmanr(drf_all, lb_all).statistic), 4),
        },
        "correlations_9_non_leaking_scored": {
            "n": int(len(scored_clean_idx)),
            "catalogue_hidden_spearman": round(float(spearmanr(ho_cat_scored, lb_scored).statistic), 4),
            "catalogue_hidden_pearson": round(float(pearsonr(ho_cat_scored, lb_scored).statistic), 4),
            "sgmc_calibrated_spearman": round(float(spearmanr(ho_sgmc_scored, lb_scored).statistic), 4),
            "sgmc_calibrated_pearson": round(float(pearsonr(ho_sgmc_scored, lb_scored).statistic), 4),
            "drift_corrected_spearman": round(float(spearmanr(ho_drf_scored, lb_scored).statistic), 4),
            "drift_corrected_pearson": round(float(pearsonr(ho_drf_scored, lb_scored).statistic), 4),
        },
        "allocated_weekly_slots": [r["candidate_id"] for r in eligible_new[:3]],
        "reserve_candidates": [r["candidate_id"] for r in eligible_new[3:]],
        "rejected_ablations": [
            r["candidate_id"]
            for r in records
            if not r.get("is_historical", False) and not r["beats_incumbent_all_holdouts"]
        ],
    }
    return diagnostics
