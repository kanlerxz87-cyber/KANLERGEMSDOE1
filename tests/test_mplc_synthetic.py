"""The existing parallel feature primitive is testable, but its lane is stopped."""
import sys
import unittest
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from kanler.mplc import phase_congruency
from kanler.lane import run_holdout


class MplcSyntheticTests(unittest.TestCase):
    def test_step_beats_noise_percentile(self):
        rng=np.random.default_rng(0);valid=np.ones((256,256),bool)
        img=rng.normal(0,1,(256,256));img[:,128:]+=3.0
        pc,_=phase_congruency(img,valid)
        noise,_=phase_congruency(rng.normal(0,1,(256,256)),valid)
        self.assertGreater(pc[128,128],np.percentile(noise,95))
        self.assertGreaterEqual(pc.min(),0);self.assertLessEqual(pc.max(),1)

    def test_stopped_lane_cannot_start_holdout(self):
        with self.assertRaisesRegex(RuntimeError,'STOP'):
            run_holdout()

if __name__=='__main__':unittest.main()
