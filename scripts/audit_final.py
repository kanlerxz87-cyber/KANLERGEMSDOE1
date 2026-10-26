import sys, json
sys.path.insert(0,'src'); sys.path.insert(0,'vendor')
import numpy as np, rasterio
from pathlib import Path
from scipy import ndimage as ndi
from scipy.stats import spearmanr
from kanler.lane import load_grid, ROOT
from gems57.validate import validate
from gems57 import metric as vmetric

grid, footprint, catalogue = load_grid()
tif = sorted((ROOT/"docs/downloads").glob("kanler-*.tif"))[-1]
receipt = validate(tif, footprint=footprint, catalogue=catalogue)
Path("evidence/validator_receipt.json").write_text(json.dumps(receipt, indent=2))
print("validator all pass:", receipt["all_checks_passed"], receipt["sha256"], receipt["emitted_positive_pixels"])
dots = np.load(ROOT/"data/cache/dots_final.npy")
prob = np.load(ROOT/"data/cache/prob_final.npy").astype(np.float32)

def dot_overlap(mine, theirs, r=3):
    # fraction of mine within r px (Euclidean) of theirs
    if theirs.sum()==0: return 0.0
    dist = ndi.distance_transform_edt(~theirs)
    return float((dist[mine] <= r).mean())

def load_raster(p):
    with rasterio.open(p) as ds: return ds.read(1)
registry = {
 "champion_h33_b2_OWNER-REPORTED-0.2778": ROOT/"data/registry_rasters/champion_h33_b2_02778.tif",
 "d28_OWNER-REPORTED-0.2600": ROOT/"data/registry_rasters/d28_02600.tif",
 "d15_OWNER-REPORTED-0.2477": ROOT/"data/scored/gems24-h25-1-dotted-h19-5-d1-5-20261002-989f59505db1-nan.tif",
 "h19_5_OWNER-REPORTED-0.1922": ROOT/"data/scored/gems19-h19-5-powerlaw-budget-multiline-corroborated-20260930-e27054cf-nan.tif",
 "h19_4_OWNER-REPORTED-0.1894": ROOT/"data/scored/gems19-h19-4-multiline-corroborated-openness-thermal-pop-20260930-691e4dfa-nan.tif",
 "h16_1_OWNER-REPORTED-0.1855": ROOT/"data/scored/gems16-h16-1-topo-geophys-baseline-ridges-20260930-df20f65e-nan.tif",
 "gems27_topo_OWNER-REPORTED-0.2449": ROOT/"data/scored/gems27-topo-gap-closure-t-v2-on-d1-5-20261002-5512495c6bd1-nan.tif",
 "lattice_s5_blanket": ROOT/"data/scored/13gems_20261001_r13-lattice-s5_v2_nan-outside.tif",
}
rng = np.random.default_rng(4)
fp_idx = np.nonzero(footprint.ravel())[0]
sample_idx = rng.choice(fp_idx, size=400000, replace=False)
rows = {}
for name_, p in registry.items():
    a = load_raster(p)
    theirs = np.isfinite(a) & (a > 0)
    rho = spearmanr(prob.ravel()[sample_idx], np.nan_to_num(a, nan=0.0).ravel()[sample_idx]).statistic
    rows[name_] = {"dots": int(theirs.sum()), "dot_overlap_3px_frac_of_mine": dot_overlap(dots, theirs),
                    "surface_spearman_sample400k": float(rho),
                    "exact_dot_intersection": int((dots & theirs).sum())}
    print(name_, rows[name_])
# SGMC off-catalogue discovery proxy (COMPUTED, not a score)
with rasterio.open(ROOT/"data/external/derived_sgmc_faults_100m_u8.tif") as ds: sgmc = ds.read(1) > 0
dist_cat = ndi.distance_transform_edt(~catalogue)
truth_sgmc = sgmc & footprint & (dist_cat > 3)
def dti_binary(pred, truth):
    r = vmetric.dti_exact(pred.astype(np.float32), truth, valid=footprint)
    return float(r["dti"])
champ = load_raster(registry["champion_h33_b2_OWNER-REPORTED-0.2778"]) > 0
base_emitted = np.load(ROOT/"data/cache/emitted_cand_b37654.npy")  # holdout-fold candidate dots (not final model)
sg = {"truth_sgmc_offcat_px": int(truth_sgmc.sum()),
      "candidate_final_DTI_on_SGMC": dti_binary(dots, truth_sgmc),
      "champion_DTI_on_SGMC": dti_binary(champ & footprint, truth_sgmc)}
print("SGMC proxy:", sg)
out = {"validator": receipt, "uniqueness_vs_registry": rows, "sgmc_proxy_COMPUTED": sg,
       "gates": {"surface_abs_spearman_max_discrete_peers": max(abs(v["surface_spearman_sample400k"]) for k_,v in rows.items() if "lattice" not in k_),
                 "dot_overlap_max_discrete_peers": max(v["dot_overlap_3px_frac_of_mine"] for k_,v in rows.items() if "lattice" not in k_),
                 "lattice_overlap_disclosed": rows["lattice_s5_blanket"]["dot_overlap_3px_frac_of_mine"]}}
Path("evidence/final_audit.json").write_text(json.dumps(out, indent=2))
print(json.dumps(out["gates"], indent=2))
