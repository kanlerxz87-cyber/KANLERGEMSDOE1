"""Regression tests for release-critical computations; no external data or slots."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import rasterio
from rasterio.transform import from_origin
from scipy.ndimage import distance_transform_edt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gems32 import submission
from gems32 import features
from gems32.features import _hessian_ridge, _hessian_both_polarities
from gems32 import holdout
from gems32.holdout import PreparedCell, HoldoutContext, evaluate_hide_and_recover
from gems32.metric import dti_exact, dti_bruteforce
from gems32.release_gate import compare_registry, promotion_decision, REQUIRED_VALIDATOR_CHECKS
from gemsdoe1.iedr import hessian_ridge


class HessianRidgeTests(unittest.TestCase):
    def test_bright_dark_rotated_and_flat(self):
        y, x = np.mgrid[-32:33, -32:33]
        bright = np.exp(-(x / 4.0)**2 / 2).astype(np.float32)
        dark = -bright
        rb = _hessian_ridge(bright, 2)
        self.assertGreater(float(rb[32,32]), .01)
        self.assertEqual(float(_hessian_ridge(dark,2)[32,32]), 0.0)
        self.assertAlmostEqual(float(_hessian_ridge(bright.T,2)[32,32]), float(rb[32,32]), places=6)
        self.assertLess(float(np.max(np.abs(_hessian_ridge(np.ones_like(bright),2)))), 0.001)
        np.testing.assert_array_equal(hessian_ridge(bright,2), rb)
        from gems32.h33 import line_response as line_both
        from gems32.h35_new import line_response as line_bright
        from gems32.pfonly import hessian_ridge as pf_bright
        from gems32.hypotheses33 import _hessian_ridge_response as hypo_bright
        self.assertGreater(float(line_both(dark,2)[32,32]), .01)
        np.testing.assert_array_equal(line_both(bright,2),_hessian_both_polarities(bright,2))
        for fn in (line_bright,pf_bright,hypo_bright):
            np.testing.assert_array_equal(fn(bright,2),rb)
            self.assertEqual(float(fn(dark,2)[32,32]),0.0)

    def test_checked_feature_cache_rejects_legacy_and_tampering(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'training_features.tif';sample=root/'sample_submission.tif'
            prof=dict(driver='GTiff',height=12,width=12,dtype='float32',crs='EPSG:32611',
                      transform=from_origin(1,12,1,1))
            with rasterio.open(source,'w',count=19,**prof) as ds:
                for i in range(1,20):ds.write(np.full((12,12),float(i),'f4'),i)
            with rasterio.open(sample,'w',count=1,nodata=np.nan,**prof) as ds:ds.write(np.zeros((12,12),'f4'),1)
            cache=root/'features.npy'
            with self.assertRaises(ValueError):features.load_checked(cache,source)
            receipt=features.build(source,cache,log=lambda _:None)
            self.assertEqual(receipt['feature_schema_version'],features.FEATURE_SCHEMA_VERSION)
            self.assertEqual(features.load_checked(cache,source).shape,(12,12,len(features.CHANNELS)))
            meta=cache.with_suffix('.npy.json');j=json.loads(meta.read_text());j['feature_schema_version']='old'
            meta.write_text(json.dumps(j))
            with self.assertRaises(ValueError):features.load_checked(cache,source)

    def test_thermal_conduit_magnetic_term_uses_magnetic_band(self):
        from gems32 import hypotheses33
        shape=(12,12);foot=np.ones(shape,bool);zero=np.zeros(shape,'f4')
        ramp=np.broadcast_to(np.arange(shape[1],dtype='f4'),shape)
        def run(mag):
            def loader(path,index,name):return {12:zero,3:mag,15:zero}[index]
            with mock.patch.object(hypotheses33,'load_band',side_effect=loader), \
                 mock.patch.object(hypotheses33,'compute_gdr_thermal_prior',return_value={'T_reservoir':np.ones(shape,'f4')}), \
                 mock.patch.object(hypotheses33,'_robust_zpos',side_effect=lambda a,f:np.where(f,a,0)):
                return hypotheses33.compute_h33_1_thermal_conduit(Path('.'),Path('.'),foot)['score']
        self.assertGreater(float((run(ramp)-run(zero)).mean()),0.001)

    def test_paleo_coordinates_use_nad83_and_floor(self):
        import zipfile
        from gemsdoe1.iedr import paleo_halo
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'paleo.zip'
            with zipfile.ZipFile(path,'w') as z:
                z.writestr('Paleo_geothermal_final.csv','Long_deg_NAD83,Lat_deg_NAD83\n-117,40\n')
            with mock.patch('rasterio.warp.transform',return_value=([1.9],[8.1])) as transform:
                result=paleo_halo(path,from_origin(0,10,1,1),(10,10),np.ones((10,10),bool),sigma=0)
            self.assertEqual(transform.call_args.args[:2],('EPSG:4269','EPSG:32611'))
            self.assertEqual(result[1,1],1);self.assertEqual(result.sum(),1)


class HoldoutTests(unittest.TestCase):
    def _cells(self):
        shape=(7,7);foot=np.ones(shape,bool);truth=np.zeros(shape,bool);truth[3,3]=True
        k=np.maximum(0,1-distance_transform_edt(~truth)/3).astype('f4')
        cells=[]
        for draw in (20,21):
            for fold in range(4):
                key=f'draw{draw}_fold{fold}';positive=(draw==20 and fold==0)
                cells.append(PreparedCell(key=key,fold=fold,seed=draw,bbox=(slice(0,7),slice(0,7)),
                    active_sub=foot,truth_coords=np.nonzero(truth if positive else np.zeros(shape,bool)),
                    k_dg_sub=k if positive else np.zeros(shape,'f4'),n_truth=int(positive)))
        return HoldoutContext(foot=foot,labels=np.zeros(shape,bool),sgmc_off=np.zeros(shape,bool),
            near_visible=np.zeros(shape,bool),quad=np.zeros(shape,int),quad_bboxes={},cells=cells,
            sgmc_truth_coords=(np.array([],int),np.array([],int)),sgmc_k_dg=np.zeros(shape),
            sgmc_n_truth=0,sgmc_quad_truth_coords={},sgmc_quad_n_truth={})

    def test_zero_truth_cells_still_count_false_positives(self):
        ctx=self._cells();pred={}
        for cell in ctx.cells:
            a=np.zeros((7,7),dtype=np.uint8);a[3,3]=1;pred[cell.key]=a
        r=evaluate_hide_and_recover(pred,ctx,grid_n=1,n_boot=20,seed=2)
        self.assertAlmostEqual(r['pooled_dti'],1/(1+.2*7),places=7)
        self.assertEqual(r['n_withheld_positives'],1)
        self.assertEqual(r['folds']['draw20_fold1']['fp'],1.0)
        self.assertEqual(r['folds']['draw20_fold1']['n_truth'],0)
        self.assertEqual(r['evaluator_version'],'GEMSDOE32-HIDE-RECOVER-v3.1')
        self.assertFalse(r['catalogue_feature_provenance_verified'])

    def test_reject_full_map_invalid_and_incomplete(self):
        ctx=self._cells();z=np.zeros((7,7),np.uint8)
        with self.assertRaises(ValueError):evaluate_hide_and_recover(z,ctx,n_boot=20)
        with self.assertRaises(ValueError):evaluate_hide_and_recover({},ctx,n_boot=20)
        bad={cell.key:z.copy() for cell in ctx.cells};bad['draw20_fold0']=z.astype(float);bad['draw20_fold0'][1,1]=np.nan
        with self.assertRaises(ValueError):evaluate_hide_and_recover(bad,ctx,n_boot=20)
        bad['draw20_fold0'][1,1]=.5
        with self.assertRaises(ValueError):evaluate_hide_and_recover(bad,ctx,n_boot=20)
        r=evaluate_hide_and_recover(z,ctx,n_boot=20,diagnostic_allow_full_map=True)
        self.assertEqual(r['prediction_mode'],'full_map_diagnostic_only')
        self.assertFalse(r['promotion_evidence'])

    def test_whole_segments_hidden(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'external').mkdir();shape=(50,50)
            lab=np.zeros(shape,'u1');lab[5:9,5]=1;lab[34:39,34]=1;lab[7:10,35]=1
            profile=dict(driver='GTiff',height=50,width=50,count=1,crs='EPSG:32611',
                         transform=from_origin(1,50,1,1))
            for path,arr in (('sample_submission.tif',np.zeros(shape,'f4')),('labels.tif',lab),
                            ('external/derived_sgmc_faults_100m_u8.tif',np.zeros(shape,'u1'))):
                with rasterio.open(root/path,'w',**profile,dtype=arr.dtype) as ds:ds.write(arr,1)
            with mock.patch.multiple(holdout,COLLAR_PX=1,DOMAIN_ERODE=1,NEAR_LABEL_PX=1):
                ctx=holdout.load_holdout_context(root,hide_frac=.5)
            for cell in ctx.cells:
                for col,lo,hi in ((5,5,9),(34,34,39),(35,7,10)):
                    part=cell.visible_full[lo:hi,col]
                    self.assertTrue(part.all() or not part.any())

    def test_fast_metric_matches_brute_force(self):
        rng=np.random.default_rng(8)
        for _ in range(5):
            y=rng.random((12,13))<.08;p=rng.random((12,13)).astype('f4');m=rng.random((12,13))>.1
            a=dti_exact(p,y,valid=m);b=dti_bruteforce(np.where(m,p,0),y&m)
            for key in ('tp','fp','fn','dti'):
                self.assertAlmostEqual(a[key],b[key],places=5)


class ReleaseGateTests(unittest.TestCase):
    def test_saturating_baseline_not_exempt_at_either_stage(self):
        rng=np.random.default_rng(7); f=np.ones((10,10),bool)
        s=rng.random(f.shape); old=rng.random(f.shape)
        dot=np.zeros_like(f);dot[2,2]=True
        lattice=np.zeros_like(f);lattice[::5,::5]=True
        registry={'calibration_lattice':(old,lattice)}
        for stage in ('surface','final'):
            r=compare_registry(s,dot,f,registry,stage=stage,inventory_complete=True)
            self.assertTrue(r['stop']);self.assertEqual(r['comparisons'][0]['within_3px_fraction'],1)
        with self.assertRaises(ValueError): compare_registry(s,None,f,registry,stage='surface')

    def test_incomplete_inventory_and_identical_surface_stop(self):
        rng=np.random.default_rng(11);f=np.ones((10,10),bool);s=rng.random(f.shape)
        d=np.zeros_like(f);d[0,0]=1;o=np.zeros_like(f);o[9,9]=1
        reg={'a':(rng.random(f.shape),o)}
        self.assertFalse(compare_registry(s,d,f,reg,inventory_complete=False)['passed'])
        self.assertTrue(compare_registry(s,d,f,reg,inventory_complete=True)['passed'])
        self.assertTrue(compare_registry(s,d,f,{'same':(s,o)},inventory_complete=True)['stop'])

    def test_nonbinary_support_and_unverified_promotion_fail_closed(self):
        rng=np.random.default_rng(5);f=np.ones((10,10),bool);s=rng.random(f.shape)
        d=np.zeros_like(f);d[0,0]=1;o=np.zeros_like(f);o[9,9]=1
        with self.assertRaises(ValueError):
            compare_registry(s,d.astype(float)*np.nan,f,{'r':(s,o)},inventory_complete=True)
        surf={'stage':'surface','passed':True,'inventory_complete':True,
              'comparisons':[{'measurable':True,'duplicate':False}]}
        final={**surf,'stage':'final'}
        score={'score_label':'HOLDOUT-DTI','evaluator_version':'test-v1',
               'catalogue_feature_provenance_verified':True,'independent_replay_sha256':'a'*64,
               'n_withheld_positives':10,'pooled_dti':.2,'ci95_cluster_bootstrap':[.1,.3]}
        old={**score,'pooled_dti':.1,'ci95_cluster_bootstrap':[.05,.15]}
        validator={'checks':{k:True for k in REQUIRED_VALIDATOR_CHECKS},
                   'all_checks_passed':True,'organizer_template_authenticated':True}
        kwargs=dict(lane='test',surface_check=surf,final_check=final,canary_aucs={'feature':.6},
                    holdout=score,incumbent=old,same_evaluation=True,validator=validator,
                    paired_delta_ci95=[.01,.1],expected_features=['feature'])
        self.assertEqual(promotion_decision(**kwargs)['verdict'],'promote')
        unverified={**score,'catalogue_feature_provenance_verified':False}
        self.assertEqual(promotion_decision(**{**kwargs,'holdout':unverified})['verdict'],'negative')
        self.assertEqual(promotion_decision(**{**kwargs,'expected_features':['feature','missing']})['verdict'],'negative')
        self.assertEqual(promotion_decision(**{**kwargs,'validator':{**validator,'organizer_template_authenticated':False}})['verdict'],'negative')
        self.assertEqual(promotion_decision(**{**kwargs,'surface_check':{**surf,'inventory_complete':False}})['verdict'],'negative')
        self.assertTrue(promotion_decision(**kwargs)['selector_required'])


class SubmissionWriterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.shape=(32,40);self.foot=np.ones(self.shape,bool);self.foot[:3,:]=0
        self.labels=np.zeros(self.shape,bool);self.labels[5,5]=1
        self.template=self.root/'template.tif'; profile=dict(driver='GTiff',height=32,width=40,count=1,
           dtype='float32',crs='EPSG:32611',transform=from_origin(100,200,100,100),nodata=np.nan)
        with rasterio.open(self.template,'w',**profile) as ds:ds.write(np.where(self.foot,0,np.nan).astype('f4'),1)
        self.out=self.root/'out'
        self.patcher=mock.patch.multiple(submission,EXPECTED_HEIGHT=32,EXPECTED_WIDTH=40,
             EXPECTED_TOTAL_PIXELS=1280,EXPECTED_FOOTPRINT_PIXELS=int(self.foot.sum()))
        self.patcher.start()
        self.meta={'candidate_id':'test','slug':'test','description':'test',
                   'submission_note_zeros':'test research only','submission_note_nan':'test research only',
                   'catalogue_hidden_mean':None,'catalogue_hidden_per_quadrant':None,
                   'sgmc_prevalence_calibrated_dti':None,'drift_corrected_holdout_mean':None,
                   'drift_corrected_per_quadrant':None,'predicted_leaderboard_dti':None,
                   'ei_drift_corrected':None,'slot_decision':'research-only'}
        self.a=np.zeros(self.shape,'f4');self.a[8,8]=.25;self.a[10,10]=.75
    def tearDown(self):self.patcher.stop();self.tmp.cleanup()
    def write(self,a=None,meta=None):
        return submission.write_submission_pair(self.a if a is None else a,self.foot,self.labels,
            template_tif=self.template,out_dir=self.out,slug='test',candidate_meta=meta or self.meta,timestamp_tag='unit')
    def test_probability_roundtrip_and_collision_refusal(self):
        import zipfile
        bundle=self.write(); self.assertTrue(bundle['zeros_tif']['all_checks_passed'])
        self.assertTrue(bundle['nan_tif']['all_checks_passed'])
        with rasterio.open(self.out/bundle['zeros_tif']['filename']) as ds:
            self.assertIsNone(ds.nodata);np.testing.assert_array_equal(ds.read(1),self.a)
        with zipfile.ZipFile(self.out/bundle['zeros_zip']['filename']) as z:
            self.assertEqual(z.namelist(),[bundle['zeros_tif']['filename']])
        self.assertEqual(len(list(self.out.iterdir())),4)
        with self.assertRaises(FileExistsError):self.write()
        self.assertEqual(len(list(self.out.iterdir())),4)
    def test_invalid_input_is_never_clipped(self):
        for value in (np.nan,np.inf,-.01,1.01):
            a=self.a.copy();a[9,9]=value
            with self.assertRaises(ValueError):self.write(a)
        a=self.a.copy();a[0,0]=1
        with self.assertRaises(ValueError):self.write(a)
        a=self.a.copy();a[5,5]=.1
        with self.assertRaises(ValueError):self.write(a)
        badfoot=self.foot.astype(float);badfoot[2,2]=np.nan
        with self.assertRaises(ValueError):
            submission.write_submission_pair(self.a,badfoot,self.labels,self.template,self.out,'test','unit',self.meta)
        badlabels=self.labels.astype(float);badlabels[8,8]=2
        with self.assertRaises(ValueError):
            submission.write_submission_pair(self.a,self.foot,badlabels,self.template,self.out,'test','unit',self.meta)
        self.assertFalse(self.out.exists() and list(self.out.iterdir()))
    def test_rollback_on_audit_and_note_failure(self):
        with mock.patch.object(submission,'audit_geotiff',side_effect=RuntimeError('audit failed')):
            with self.assertRaises(RuntimeError):self.write()
        self.assertEqual(list(self.out.iterdir()),[])
        meta={**self.meta,'submission_note_zeros':'x'*141}
        with self.assertRaises(ValueError):self.write(meta=meta)
        self.assertEqual(list(self.out.iterdir()),[])
    def test_rollback_on_late_publish_collision(self):
        real_link=submission.os.link; calls=[]
        def fail_at_fourth(src,dst):
            calls.append(dst)
            if len(calls)==4:raise FileExistsError('raced')
            return real_link(src,dst)
        with mock.patch.object(submission.os,'link',side_effect=fail_at_fourth):
            with self.assertRaises(FileExistsError):self.write()
        self.assertEqual(list(self.out.iterdir()),[])


class RestoreTests(unittest.TestCase):
    def test_hash_size_path_and_atomic_failure(self):
        import hashlib
        sys.path.insert(0,str(ROOT/'scripts'))
        import restore_data
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'root';root.mkdir()
            class Fetch:
                def fetch(self,repo,ref,path,destination):destination.write_bytes(b'expected')
            entry={'id':'one','dest':'dir/one.bin','group':'core','repo':'a/b','ref':'a'*40,
                   'path':'file.bin','sha256':hashlib.sha256(b'expected').hexdigest(),'bytes':8}
            result=restore_data.restore_entry(entry,root,Fetch())
            self.assertEqual(result['status'],'restored')
            self.assertEqual(restore_data.restore_entry(entry,root,Fetch())['status'],'present')
            with self.assertRaises(ValueError):restore_data.restore_entry({**entry,'bytes':9},root,Fetch())
            with self.assertRaises(ValueError):restore_data.restore_entry({**entry,'dest':'../escape'},root,Fetch())
            bad={**entry,'dest':'dir/bad.bin','sha256':'b'*64}
            with self.assertRaises(ValueError):restore_data.restore_entry(bad,root,Fetch())
            self.assertFalse((root/'dir/bad.bin').exists())
            self.assertFalse((root/'dir/bad.bin.assembling').exists())

if __name__=='__main__':unittest.main()
