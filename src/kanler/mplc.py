"""MPLC: multi-scale monogenic local-phase congruency features.

Kovesi-style phase congruency.  For each source field, oriented log-Gabor
filters (6 orientations x wavelengths 8/20/50 px, one-sided in the frequency
plane so the inverse FFT is a quadrature even/odd pair) give, per orientation
o, summed even/odd responses E_o = sqrt((sum_s even)^2 + (sum_s odd)^2) and
summed amplitudes A_o = sum_s sqrt(even^2 + odd^2).  PC = sum_o E_o /
sum_o A_o in [0, 1]: near 1 where all scales agree on the same local phase
(a step/line discontinuity), low for incoherent texture.  Unlike gradient
magnitude, PC is contrast-invariant, so low-amplitude buried steps are not
buried under high-contrast shallow ones.
"""
from __future__ import annotations
import numpy as np
from scipy import ndimage as ndi

WAVELENGTHS = (8.0, 20.0, 50.0)
N_ORIENT = 6
SIGMA_ONF = 0.65       # log-Gabor radial bandwidth (Kovesi convention)
SIGMA_THETA = 1.0      # angular spread (rad)


def phase_congruency(img: np.ndarray, valid: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return (PC, log mean amplitude) float32 arrays for one source field."""
    x = np.asarray(img, np.float64)
    med = np.median(x[valid]) if valid.any() else 0.0
    x = np.where(np.isfinite(x), x, med)
    lo, hi = np.percentile(x[valid], [1, 99]) if valid.any() else (x.min(), x.max())
    x = np.clip(x, lo, hi)
    x = x - x.mean()
    h, w = x.shape
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.fftfreq(w)[None, :]
    f = np.sqrt(fx * fx + fy * fy)
    theta = np.arctan2(fy, fx)  # wavevector angle
    F = np.fft.fft2(x)
    radial_by_scale = []
    for wl in WAVELENGTHS:
        f0 = 1.0 / wl
        radial = np.exp(-(np.log(np.maximum(f, 1e-12) / f0) ** 2) / (2 * np.log(SIGMA_ONF) ** 2))
        radial[0, 0] = 0.0
        radial_by_scale.append(radial)
    sum_e = np.zeros(x.shape); sum_a = np.zeros(x.shape)
    for o in range(N_ORIENT):
        theta_o = o * np.pi / N_ORIENT  # filter normal direction
        dtheta = np.arctan2(np.sin(theta - theta_o), np.cos(theta - theta_o))
        angular = np.exp(-(dtheta ** 2) / (2 * SIGMA_THETA ** 2))  # one lobe only -> quadrature pair
        even_sum = np.zeros(x.shape); odd_sum = np.zeros(x.shape); amp_sum = np.zeros(x.shape)
        amp_max = np.zeros(x.shape)
        for radial in radial_by_scale:
            resp = np.fft.ifft2(F * radial * angular)
            even_sum += resp.real; odd_sum += resp.imag
            a = np.abs(resp); amp_sum += a; amp_max = np.maximum(amp_max, a)
        # Kovesi frequency-spread weight: penalise responses present at only one scale
        spread = amp_sum / np.maximum(amp_max * len(radial_by_scale), 1e-12)
        weight = 1.0 / (1.0 + np.exp(-(spread - 0.5) * 10.0))
        sum_e += weight * np.sqrt(even_sum ** 2 + odd_sum ** 2)
        sum_a += weight * amp_sum
    pc = sum_e / np.maximum(sum_a, 1e-12)
    pc = np.where(valid, np.clip(pc, 0, 1), 0.0).astype(np.float32)
    amp = np.where(valid, np.log1p(sum_a / (len(WAVELENGTHS) * N_ORIENT)), 0.0).astype(np.float32)
    return pc, amp


def orientation_coherence(img: np.ndarray, valid: np.ndarray, smooth_px: float = 3.0, tensor_px: float = 5.0) -> np.ndarray:
    """Structure-tensor coherence (l1-l2)/(l1+l2) of the smoothed gradient, in [0,1]."""
    x = np.asarray(img, np.float64)
    med = np.median(x[valid]) if valid.any() else 0.0
    x = np.where(np.isfinite(x), x, med)
    xs = ndi.gaussian_filter(x, smooth_px)
    gy, gx = np.gradient(xs)
    jxx = ndi.gaussian_filter(gx * gx, tensor_px)
    jyy = ndi.gaussian_filter(gy * gy, tensor_px)
    jxy = ndi.gaussian_filter(gx * gy, tensor_px)
    tr = jxx + jyy
    disc = np.sqrt(np.maximum((jxx - jyy) ** 2 + 4 * jxy * jxy, 0.0))
    coh = np.where(tr > 1e-12, disc / np.maximum(tr, 1e-12), 0.0)
    return np.where(valid, coh, 0.0).astype(np.float32)


MPLC_NAMES = ["pc_rtp", "pc_grav", "pc_dem", "pc_min", "pc_mean", "orient_coh_rtp"]


def build_mplc(features_path, sample_path, out_path) -> list[str]:
    import rasterio
    with rasterio.open(sample_path) as ds:
        footprint = np.isfinite(ds.read(1))
    with rasterio.open(features_path) as ds:
        sources = [ds.read(2), ds.read(13), ds.read(12)]  # rtp, iso_grav_anom, det_elev
    pcs = []
    for arr in sources:
        pc, _ = phase_congruency(arr, footprint)
        pcs.append(pc)
    coh = orientation_coherence(sources[0], footprint)
    stack = np.stack(pcs + [np.minimum.reduce(pcs), np.mean(pcs, axis=0), coh])
    out = np.lib.format.open_memmap(out_path, mode="w+", dtype=np.float32, shape=(len(MPLC_NAMES),) + footprint.shape)
    out[:] = stack
    out.flush()
    return MPLC_NAMES
