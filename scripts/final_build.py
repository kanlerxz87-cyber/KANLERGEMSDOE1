import sys, json, hashlib, time
sys.path.insert(0,'src'); sys.path.insert(0,'vendor')
import numpy as np
from pathlib import Path
from scipy import ndimage as ndi
from kanler.lane import load_grid, BASE_SPECS, band_window, extract_points, emit_dots, ROOT, PATHS
from sklearn.ensemble import HistGradientBoostingClassifier
import rasterio
from rasterio.windows import Window

grid, footprint, catalogue = load_grid()
mplc = np.load(ROOT/"data/cache/mplc.npy", mmap_mode="r")
rng = np.random.default_rng(20261026)
pos = np.nonzero(catalogue)
neg_pool = np.nonzero(footprint & ~ndi.binary_dilation(catalogue, iterations=3))
pick = rng.choice(len(neg_pool[0]), size=3*len(pos[0]), replace=False)
ys = np.concatenate([pos[0], neg_pool[0][pick]]); xs = np.concatenate([pos[1], neg_pool[1][pick]])
y = np.concatenate([np.ones(len(pos[0]), np.int8), np.zeros(len(pick), np.int8)])
print(f"train {len(y)} ({int((y==1).sum())} pos)", flush=True)
X = extract_points(ys, xs, True, mplc)
model = HistGradientBoostingClassifier(max_iter=250, learning_rate=0.06, max_leaf_nodes=31,
                                       min_samples_leaf=40, l2_regularization=1.0, random_state=7)
wts = np.where(y==1, len(y)/(2*(y==1).sum()), len(y)/(2*(y==0).sum()))
model.fit(X, y, sample_weight=wts)
# permutation-free importance proxy: use model? HGB has no importance; skip
H, W = footprint.shape
prob = np.zeros((H, W), np.float32)
step = 128
for r0 in range(0, H, step):
    r1 = min(H, r0+step)
    cols = []
    for key, band in BASE_SPECS:
        cols.append(band_window(key, band, (r0, r1, 0, W)).ravel())
    for i in range(mplc.shape[0]):
        cols.append(np.asarray(mplc[i][r0:r1, :]).ravel())
    prob[r0:r1] = model.predict_proba(np.stack(cols, axis=1))[:, 1].reshape(r1-r0, W)
    print(f"rows {r1}/{H}", flush=True)
prob = np.where(footprint, prob, 0).astype(np.float32)
np.save(ROOT/"data/cache/prob_final.npy", prob.astype(np.float16))
allowed = footprint & ~ndi.binary_dilation(catalogue, iterations=2)
dots = emit_dots(prob, allowed, 37654)
print("dots", int(dots.sum()), "on catalogue", int((dots & catalogue).sum()))
np.save(ROOT/"data/cache/dots_final.npy", dots)
out = np.where(dots, 1.0, 0.0).astype(np.float32)
stamp = "20261026"
sha = hashlib.sha256(out.tobytes()).hexdigest()[:12]
name = f"kanler-mplc-hgb-37654-{stamp}-{sha}-zeros"
from gems57.grid import write_geotiff
dest = ROOT/f"docs/downloads/{name}.tif"
info = write_geotiff(dest, out)
print("written", dest, info)
(Path(ROOT/"evidence/final_build.json")).write_text(json.dumps(
    {"name": name, "dots": int(dots.sum()), "array_sha256_12": sha}, indent=2))
print("NAME", name)
