"""Passage-local regression: failed distant hosts must not block wall openings."""
import ast
import os
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock
import sys
ROOT=os.path.join(os.path.dirname(__file__),'..','HDL Openings.extension','lib','hdl_openings')
sys.path.insert(0,os.path.dirname(ROOT))
from hdl_openings import synchronization as sync


def load_function(file,name,namespace):
    with open(os.path.join(ROOT,file)) as f:tree=ast.parse(f.read())
    tree.body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name]
    exec(compile(tree,file,'exec'),namespace)
    return namespace[name]


class LocalCoverageTests(unittest.TestCase):
    def setUp(self):
        self.probe=NS(Dispose=Mock())
        self.bounds=[(0,1)]*3
        self.transform=object()
        self.source=NS(link=NS(Name='Architecture.rvt'),transform=self.transform)
        self.element=NS(Id=10260227)
        self.solid=object()
        self.geo=NS(opening_volume=Mock(return_value=self.probe),
                    bbox=lambda items:self.bounds,
                    solids=Mock(return_value=[self.solid]),intersect=Mock(return_value=None))
        factory=load_function('model.py','local_host_coverage',dict(geo=self.geo,id_value=lambda i:i))
        self.check=factory({'link:floor':(self.source,self.element)},
                           {'link:floor':[(0,10)]*3},None)
        self.payload=dict(mep_uid='pipe',state={'local':'opening'},participants=[dict(source='link',uid='wall')])
    def test_overlapping_boxes_without_solid_overlap_allow_creation(self):
        self.assertIsNone(self.check(self.payload,'link:floor'))
        self.geo.intersect.assert_called_once_with(self.probe,self.solid)
        self.probe.Dispose.assert_called_once()
    def test_distant_passage_is_not_blocked_by_same_pipe_other_passage(self):
        self.bounds=[(20,21)]*3
        self.assertIsNone(self.check(self.payload,'link:floor'))
        self.geo.solids.assert_not_called()
        self.bounds=[(0,1)]*3
        overlap=NS(Dispose=Mock());self.geo.intersect.return_value=overlap
        reason=self.check(self.payload,'link:floor')
        self.assertIn('intersects',reason)
        self.assertIn('Architecture.rvt',reason);self.assertIn('10260227',reason)
    def test_solids_use_link_transform_and_are_cached(self):
        self.check(self.payload,'link:floor');self.check(self.payload,'link:floor')
        self.geo.solids.assert_called_once_with(self.element,self.transform)
    def test_boolean_failure_preserves_uncertainty(self):
        self.geo.intersect.side_effect=RuntimeError('kernel failure')
        self.assertIn('uncertain',self.check(self.payload,'link:floor'))
    def test_missing_solid_preserves_uncertainty(self):
        self.geo.solids.return_value=[]
        self.assertIn('unavailable',self.check(self.payload,'link:floor'))
    def test_legacy_unrelated_host_does_not_block(self):
        self.payload.pop('state')
        self.assertIsNone(self.check(self.payload,'link:floor'))
        self.payload['participants'][0]['uid']='floor'
        self.assertIn('legacy',self.check(self.payload,'link:floor'))
    def test_reconciliation_keeps_existing_when_local_boolean_is_uncertain(self):
        # Integration with actual reconciliation policy: no delete or replace.
        from test_synchronization import payload
        p=payload();old=dict(payload=p,actual=p['state']);new=dict(payload=p)
        actions=sync.reconcile([old],[new],lambda p:'Local geometry check uncertain',.001,.001)
        self.assertEqual(sorted(a['kind'] for a in actions),['retain','skip'])


class Vector:
    def __init__(self,*v):self.v=v
    def DotProduct(self,other):return sum(a*b for a,b in zip(self.v,other.v))


class OpeningVolumeTests(unittest.TestCase):
    def volume(self,family,shape):
        self.prism=Mock();self.cylinder=Mock()
        f=load_function('geometry.py','opening_volume',dict(DB=NS(XYZ=Vector),EPS=1e-9,
            UnsupportedGeometry=ValueError,prism=self.prism,cylinder=self.cylinder))
        f(dict(insertion=[10,20,30],x=[1,0,0],y=[0,1,0],normal=[0,0,1],
               family=family,shape=shape,width=4,height=6,diameter=4,depth=2))
    def test_wall_rect_bottom_origin(self):
        self.volume('BL Opening Rect Wall','rect')
        self.assertEqual(self.prism.call_args.args[3:],((8,12),(20,26),(30,32)))
    def test_floor_rect_top_center_origin(self):
        self.volume('BL Opening Rect Floor','rect')
        self.assertEqual(self.prism.call_args.args[3:],((8,12),(17,23),(28,30)))
    def test_round_wall_center_origin(self):
        self.volume('BL Opening Round Wall','round')
        self.assertEqual(self.cylinder.call_args.args[4:],(4,(30,32)))
    def test_round_floor_top_origin(self):
        self.volume('BL Opening Round Floor','round')
        self.assertEqual(self.cylinder.call_args.args[4:],(4,(28,30)))

if __name__=='__main__':unittest.main()
