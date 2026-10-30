import copy
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..','HDL Openings.extension','lib'))
from hdl_openings import settings
ROOT=os.path.join(os.path.dirname(__file__),'..','HDL Openings.extension','settings.json')
with open(ROOT) as f:DEFAULT=json.load(f)

class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=os.path.join(self.temp.name,'settings.json')
    def tearDown(self):self.temp.cleanup()
    def write(self,data):
        # atomic replace simulates common editor behaviour and changes file identity
        p=self.path+'.tmp'
        with open(p,'w') as f:json.dump(data,f)
        os.replace(p,self.path)
    def test_default_and_units(self):
        cfg=settings.validate(DEFAULT)
        self.assertAlmostEqual(cfg.max_core_depth*304.8,1000)
        self.assertAlmostEqual(cfg.cores[0]*304.8,25.4)
        self.assertNotIn(2.5/12,cfg.cores);self.assertNotIn(3.5/12,cfg.cores)
    def test_immutable_snapshot(self):
        cfg=settings.validate(DEFAULT)
        with self.assertRaises(AttributeError):cfg.gap=1
        with self.assertRaises(AttributeError):cfg.families.round_wall='other'
    def test_unchanged_file_not_read(self):
        self.write(DEFAULT);a,w,reload=settings.load(self.path)
        with patch.object(settings,'_read_stable',side_effect=AssertionError('must not read')):
            b,w,reload=settings.load(self.path)
        self.assertIs(a,b);self.assertFalse(reload);self.assertIsNone(w)
    def test_hot_reload_preserves_old_snapshot(self):
        self.write(DEFAULT);a,_,_=settings.load(self.path)
        changed=copy.deepcopy(DEFAULT);changed['rect_size_step_mm']=25
        self.write(changed);b,w,reload=settings.load(self.path)
        self.assertTrue(reload);self.assertIsNone(w)
        self.assertAlmostEqual(a.rect_step*304.8,50)
        self.assertAlmostEqual(b.rect_step*304.8,25)
        self.assertNotEqual(a.fingerprint,b.fingerprint)
    def test_invalid_update_retains_cache(self):
        self.write(DEFAULT);a,_,_=settings.load(self.path)
        self.write({'broken':True});b,w,reload=settings.load(self.path)
        self.assertIs(a,b);self.assertTrue(w);self.assertFalse(reload)
    def test_unchanged_invalid_update_not_reparsed(self):
        self.write(DEFAULT);settings.load(self.path);self.write({});settings.load(self.path)
        with patch.object(settings,'_read_stable',side_effect=AssertionError('must not parse')):
            _,w,_=settings.load(self.path)
        self.assertTrue(w)
    def test_missing_without_cache_blocks(self):
        with self.assertRaises(settings.SettingsError):settings.load(self.path)
    def test_deleted_with_cache_retains(self):
        self.write(DEFAULT);a,_,_=settings.load(self.path);os.remove(self.path)
        b,w,_=settings.load(self.path);self.assertIs(a,b);self.assertTrue(w)
    def test_corrupt_json(self):
        with open(self.path,'w') as f:f.write('{')
        with self.assertRaises(settings.SettingsError):settings.load(self.path)
    def test_duplicate_keys(self):
        with open(self.path,'w') as f:f.write('{"schema_version":1,"schema_version":1}')
        with self.assertRaises(settings.SettingsError):settings.load(self.path)
    def test_nan_and_infinity(self):
        for v in [float('nan'),float('inf'),-float('inf')]:
            d=copy.deepcopy(DEFAULT);d['gap_mm']=v
            with self.assertRaises(settings.SettingsError):settings.validate(d)
    def test_boolean_and_string_numbers_rejected(self):
        for v in [True,'50',None]:
            d=copy.deepcopy(DEFAULT);d['gap_mm']=v
            with self.assertRaises(settings.SettingsError):settings.validate(d)
    def test_ranges(self):
        for key,value in [('clearance_mm',-1),('rect_size_step_mm',0),('max_core_depth_mm',0),('k_slope',.9),('gap_mm',1e30)]:
            d=copy.deepcopy(DEFAULT);d[key]=value
            with self.assertRaises(settings.SettingsError):settings.validate(d)
    def test_empty_duplicate_negative_cores(self):
        for values in [[],[1,1],[-1],['1']]:
            d=copy.deepcopy(DEFAULT);d['core_diameters_inch']=values
            with self.assertRaises(settings.SettingsError):settings.validate(d)
    def test_unknown_schema_and_field(self):
        for change in [{'schema_version':2},{'schema_version':True},{'unknown':5}]:
            d=copy.deepcopy(DEFAULT);d.update(change)
            with self.assertRaises(settings.SettingsError):settings.validate(d)
    def test_invalid_family_names(self):
        d=copy.deepcopy(DEFAULT);d['families']['round_wall']=' '
        with self.assertRaises(settings.SettingsError):settings.validate(d)
    def test_size_limit(self):
        with open(self.path,'wb') as f:f.write(b' '*(settings.MAX_BYTES+1))
        with self.assertRaises(settings.SettingsError):settings.load(self.path)
    def test_file_changes_during_read(self):
        self.write(DEFAULT);before=settings._stamp(self.path)
        after=tuple(list(before[:1])+[before[1]+1]+list(before[2:]))
        with patch.object(settings,'_stamp',return_value=after):
            with self.assertRaises(settings.SettingsError):settings._read_stable(self.path,before)
    def test_utf8_bom(self):
        with open(self.path,'wb') as f:f.write(b'\xef\xbb\xbf'+json.dumps(DEFAULT).encode('utf8'))
        cfg,w,_=settings.load(self.path);self.assertIsNone(w)
    def test_deep_json_rejected_before_parser(self):
        with open(self.path,'w') as f:f.write('['*1000+'0'+']'*1000)
        with patch.object(settings.json,'loads',side_effect=AssertionError('parser must not run')):
            with self.assertRaises(settings.SettingsError):settings.load(self.path)
    def test_depth_guard_ignores_brackets_in_strings(self):
        settings._check_depth('{"x":"'+('['*100)+'"}')
    def test_sorted_cores(self):
        d=copy.deepcopy(DEFAULT);d['core_diameters_inch']=[3,1,2]
        self.assertEqual(settings.validate(d).cores,(1/12,2/12,3/12))

    def test_sync_tolerances_and_backward_compatible_json(self):
        d=copy.deepcopy(DEFAULT)
        d.pop('sync_length_tolerance_mm');d.pop('sync_angle_tolerance_deg')
        cfg=settings.validate(d)
        self.assertAlmostEqual(cfg.sync_length*304.8,.1)
        self.assertGreater(cfg.sync_direction,0)
    def test_invalid_sync_tolerances(self):
        for key,value in [('sync_length_tolerance_mm',0),('sync_angle_tolerance_deg',True),
                          ('sync_angle_tolerance_deg',2),('sync_length_tolerance_mm',float('nan'))]:
            d=copy.deepcopy(DEFAULT);d[key]=value
            with self.assertRaises(settings.SettingsError):settings.validate(d)
    def test_sync_tolerance_hot_reload(self):
        self.write(DEFAULT);a,_,_=settings.load(self.path)
        changed=copy.deepcopy(DEFAULT);changed['sync_length_tolerance_mm']=.2
        self.write(changed);b,w,reloaded=settings.load(self.path)
        self.assertTrue(reloaded);self.assertIsNone(w)
        self.assertAlmostEqual(b.sync_length,2*a.sync_length)

    def test_through_all_accepts_only_integer_zero_or_one(self):
        for value in (0,1):
            d=copy.deepcopy(DEFAULT);d['ThroughAll']=value
            self.assertEqual(settings.validate(d).through_all,bool(value))
        for value in (True,False,2,-1,'1',None,1.0):
            d=copy.deepcopy(DEFAULT);d['ThroughAll']=value
            with self.assertRaises(settings.SettingsError):settings.validate(d)
    def test_old_json_defaults_to_full_group(self):
        d=copy.deepcopy(DEFAULT);d.pop('ThroughAll',None)
        self.assertTrue(settings.validate(d).through_all)
    def test_through_all_hot_reload_without_mutating_run_snapshot(self):
        d=copy.deepcopy(DEFAULT);d['ThroughAll']=1;self.write(d)
        a,_,_=settings.load(self.path)
        d['ThroughAll']=0;self.write(d)
        b,w,reloaded=settings.load(self.path)
        self.assertTrue(reloaded);self.assertIsNone(w)
        self.assertTrue(a.through_all);self.assertFalse(b.through_all)

if __name__=='__main__':unittest.main()
