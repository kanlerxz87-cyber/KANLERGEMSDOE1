import sys
sys.path.insert(0, "src")
import numpy as np
from kanler.mplc import phase_congruency

def test_step_beats_noise_percentile():
    rng = np.random.default_rng(0)
    valid = np.ones((256, 256), bool)
    img = rng.normal(0, 1, (256, 256)); img[:, 128:] += 3.0
    pc, _ = phase_congruency(img, valid)
    noise, _ = phase_congruency(rng.normal(0, 1, (256, 256)), valid)
    assert pc[128, 128] > np.percentile(noise, 95)
    assert pc.min() >= 0.0 and pc.max() <= 1.0
