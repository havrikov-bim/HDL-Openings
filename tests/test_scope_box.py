import ast
import math
import os
import sys
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock
sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..','HDL Openings.extension','lib'))
from hdl_openings.scope_box import Region,ScopeBoxError,from_element

def segments(angle=0):
    c,s=math.cos(angle),math.sin(angle)
    def world(p):return(c*p[0]-s*p[1],s*p[0]+c*p[1],p[2])
    vertices={(i,j,k):world((2*i-1,2*j-1,2*k-1)) for i in (0,1) for j in (0,1) for k in (0,1)}
    result=[]
    for key,p in vertices.items():
        for index in range(3):
            if key[index]==0:
                end=list(key);end[index]=1
                result.append((p,vertices[tuple(end)]))
    return result

def volume(center=(0,0,0),x=(1,0,0),y=(0,1,0),normal=(0,0,1),width=1,height=1,depth=1,shape='rect'):
    return dict(center=center,x=x,y=y,normal=normal,width=width,height=height,depth=depth,shape=shape)

class RegionTests(unittest.TestCase):
    def setUp(self):self.region=Region('box','uid',segments())
    def test_inside_rectangular_volume(self):self.assertTrue(self.region.contains_volume(**volume()))
    def test_complete_volume_not_just_center_must_be_inside(self):
        self.assertFalse(self.region.contains_volume(**volume(center=(.8,0,0))))
    def test_height_is_enforced(self):
        self.assertFalse(self.region.contains_volume(**volume(center=(0,0,1))))
    def test_boundary_included(self):
        self.assertTrue(self.region.contains_volume(**volume(width=2,height=2,depth=2)))
    def test_just_outside_boundary_rejected(self):
        self.assertFalse(self.region.contains_volume(**volume(width=2.00001)))
    def test_rotated_scope_rejects_point_inside_its_world_aabb(self):
        region=Region('rotated','uid',segments(math.pi/4))
        self.assertFalse(region.contains_volume(**volume(center=(1.2,1.2,0),width=.05,height=.05,depth=.05)))
    def test_rotated_scope_accepts_actual_inside_volume(self):
        region=Region('rotated','uid',segments(math.pi/4))
        self.assertTrue(region.contains_volume(**volume(center=(.3,.3,0),width=.1,height=.1,depth=.1)))
    def test_round_support_is_exact_not_rotated_square_corners(self):
        c=math.sqrt(.5)
        self.assertTrue(self.region.contains_volume(**volume(x=(c,c,0),y=(-c,c,0),width=1.9,height=1.9,
                                                           depth=.4,shape='round')))
    def test_tilted_cylinder_support_includes_depth(self):
        c=math.sqrt(.5)
        self.assertFalse(self.region.contains_volume(**volume(x=(c,0,-c),normal=(c,0,c),y=(0,1,0),
                                                              width=1.8,height=1.8,depth=1.9,shape='round')))
    def test_long_mep_bounds_crossing_box_are_kept(self):
        self.assertTrue(self.region.overlaps_bounds([(-10,10),(-.1,.1),(-.1,.1)]))
    def test_outside_mep_bounds_rejected(self):
        self.assertFalse(self.region.overlaps_bounds([(10,11),(10,11),(0,1)]))
    def test_unknown_bounds_not_silently_omitted(self):self.assertTrue(self.region.overlaps_bounds(None))
    def test_rotated_scope_broad_phase_not_only_world_aabb(self):
        region=Region('rotated','uid',segments(math.pi/4))
        self.assertFalse(region.overlaps_bounds([(1.2,1.3),(1.2,1.3),(0,.1)]))
    def test_wall_state_origin_converted_to_center(self):
        state=dict(insertion=(0,-.5,-.5),x=(1,0,0),y=(0,0,1),normal=(0,1,0),
                   width=1,height=1,depth=1,shape='rect')
        self.assertTrue(self.region.contains_state(state,True))
        state['insertion']=(0,-.5,.8)
        self.assertFalse(self.region.contains_state(state,True))
    def test_floor_state_depth_is_below_ref_level(self):
        state=dict(insertion=(0,0,.5),x=(1,0,0),y=(0,1,0),normal=(0,0,1),
                   width=1,height=1,depth=1,shape='rect')
        self.assertTrue(self.region.contains_state(state,False))
        state['insertion']=(0,0,-.9)
        self.assertFalse(self.region.contains_state(state,False))
    def test_round_wall_state_uses_center_not_bottom_of_diameter(self):
        state=dict(insertion=(0,-.5,0),x=(1,0,0),y=(0,0,1),normal=(0,1,0),
                   diameter=1,depth=1,shape='round')
        self.assertTrue(self.region.contains_state(state,True))
    def test_round_floor_state(self):
        state=dict(insertion=(0,0,.5),x=(1,0,0),y=(0,1,0),normal=(0,0,1),
                   diameter=1,depth=1,shape='round')
        self.assertTrue(self.region.contains_state(state,False))
    def test_incomplete_geometry_fails_without_aabb_fallback(self):
        with self.assertRaises(ScopeBoxError):Region('bad','uid',[((0,0,0),(1,0,0))])
    def test_nonorthogonal_geometry_rejected(self):
        with self.assertRaises(ScopeBoxError):Region('bad','uid',segments()+[((0,0,0),(1,1,0))])
    def test_actual_state_unavailable_is_not_accepted(self):
        with self.assertRaises(ScopeBoxError):self.region.contains_state(None,True)

class GeometryAdapterTests(unittest.TestCase):
    def test_reads_rotated_scope_lines_not_world_bounding_box(self):
        class Line:
            def __init__(self,a,b):self.points=(a,b)
            def GetEndPoint(self,i):
                p=self.points[i];return NS(X=p[0],Y=p[1],Z=p[2])
        class Instance:pass
        db=NS(Options=lambda:NS(),Line=Line,GeometryInstance=Instance)
        element=NS(Name='scope',UniqueId='uid',get_Geometry=lambda options:[Line(a,b) for a,b in segments(math.pi/4)],
                   get_BoundingBox=Mock(side_effect=AssertionError('Do not use world AABB')))
        region=from_element(element,db)
        self.assertFalse(region.contains_volume(**volume(center=(1.2,1.2,0),width=.05,height=.05,depth=.05)))
        element.get_BoundingBox.assert_not_called()

class SelectionTests(unittest.TestCase):
    def setUp(self):
        path=os.path.join(os.path.dirname(__file__),'..','HDL Openings.extension','lib','hdl_openings','command.py')
        with open(path) as f:tree=ast.parse(f.read())
        tree.body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='choose_scope']
        self.boxes=[NS(Name='Scope',Id=1),NS(Name='Scope',Id=2)]
        outer=self
        class Collector:
            def __init__(self,doc):pass
            def OfCategory(self,category):return self
            def WhereElementIsNotElementType(self):return outer.boxes
        self.forms=NS(alert=Mock(),SelectFromList=NS(show=Mock(return_value='Scope [2]')))
        self.adapter=Mock(return_value='region')
        ns=dict(DB=NS(FilteredElementCollector=Collector,BuiltInCategory=NS(OST_VolumeOfInterest=1)),
                model=NS(id_value=lambda v:v),forms=self.forms,scope_box=NS(from_element=self.adapter))
        exec(compile(tree,path,'exec'),ns);self.choose=ns['choose_scope']
    def test_duplicate_names_resolve_by_unique_element_id(self):
        self.assertEqual(self.choose('doc'),'region')
        self.assertIs(self.adapter.call_args.args[0],self.boxes[1])
    def test_cancel_does_not_read_geometry(self):
        self.forms.SelectFromList.show.return_value=None
        self.assertIsNone(self.choose('doc'));self.adapter.assert_not_called()
    def test_no_scope_boxes_stops_without_geometry(self):
        self.boxes=[]
        self.assertIsNone(self.choose('doc'));self.forms.alert.assert_called_once();self.adapter.assert_not_called()

if __name__=='__main__':unittest.main()
