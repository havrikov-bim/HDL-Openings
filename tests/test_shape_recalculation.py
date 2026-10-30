"""Run the real plan_group with analytical sections and controlled solids."""
import ast
import json
import math
import os
import sys
import unittest
from types import SimpleNamespace as NS
sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..','HDL Openings.extension','lib'))
from hdl_openings import settings,synchronization as sync
from hdl_openings.math_core import insertion_coordinates,may_extend_group
from hdl_openings.section_math import swept_range,layer_normal_interval
from hdl_openings.opening_math import ceil_step,choose_round,round_requirement

class V:
    def __init__(self,x=0,y=0,z=0):self.X=x;self.Y=y;self.Z=z
    def Multiply(self,k):return V(self.X*k,self.Y*k,self.Z*k)
    def Add(self,b):return V(self.X+b.X,self.Y+b.Y,self.Z+b.Z)
    def Subtract(self,b):return self.Add(b.Multiply(-1))
    def DotProduct(self,b):return self.X*b.X+self.Y*b.Y+self.Z*b.Z

def xyz(v):return(v.X,v.Y,v.Z)

class ShapeRecalculationTests(unittest.TestCase):
    def setUp(self):
        root=os.path.join(os.path.dirname(__file__),'..','HDL Openings.extension')
        with open(os.path.join(root,'settings.json')) as f:self.cfg=settings.validate(json.load(f))
        self.normal=V(0,1,0);self.x=V(1,0,0);self.z=V(0,0,1)
        self.thickness=200/304.8;self.empty_circle=False
        solid=NS(nr=(0.,self.thickness))
        self.layer=dict(index=0,width=self.thickness,low=0.,high=self.thickness,solids=[solid])
        self.host=NS(key='CURRENT:wall',normal=self.normal,base_index=0,has_structure_layer=True,is_structural=True,
            wall=True,definition='a'*64,source=NS(key='CURRENT'),element=NS(UniqueId='wall'),
            layer_data=[self.layer],bounds=None,support=lambda i:0.)
        self.group=(0.,self.thickness,[dict(host=self.host,layer=self.layer,hits=[solid])])
        def intersect(a,b):
            if getattr(a,'circular',False) and self.empty_circle:return None
            low=max(a.nr[0],b.nr[0]);high=min(a.nr[1],b.nr[1])
            return NS(nr=(low,high)) if high>low else None
        geo=NS(frame=lambda *args:(self.x,self.z),
            combined_range=lambda ss,d:(min(s.nr[0] for s in ss),max(s.nr[1] for s in ss)),
            prism=lambda xx,yy,nn,xr,yr,nr:NS(nr=nr),
            cylinder=lambda xx,yy,nn,c,d,nr:NS(nr=nr,circular=True),
            bbox=lambda solids:None,overlaps=lambda a,b:True,intersect=intersect)
        path=os.path.join(root,'lib','hdl_openings','engine.py')
        with open(path) as f:tree=ast.parse(f.read())
        tree.body=[a for a in tree.body if not isinstance(a,(ast.Import,ast.ImportFrom))]
        ns=dict(geo=geo,EPS=1e-7,ceil_step=ceil_step,choose_round=choose_round,
            round_requirement=round_requirement,math=math,insertion_coordinates=insertion_coordinates,
            may_extend_group=may_extend_group,layer_normal_interval=layer_normal_interval)
        exec(compile(tree,path,'exec'),ns);self.calculate_group=ns['plan_group']
    def calculate(self,od,hosts=None):
        angle=math.radians(3);a=V(math.sin(angle),math.cos(angle),0);u=V(math.cos(angle),-math.sin(angle),0)
        m=NS(origin=V(),axis=a,u=u,v=self.z,length=2.,hw=od/609.6,hh=od/609.6,circular=True,
            round_eligible=True,insulation=0.,key='CURRENT:pipe',source=NS(key='CURRENT'),
            element=NS(UniqueId='pipe'),axis_trace=lambda nn,l,h:(h-l)/a.DotProduct(nn))
        m.sweep=lambda nn,l,h,d:swept_range(xyz(m.origin),xyz(a),xyz(u),xyz(self.z),m.hw,m.hh,
                                           True,xyz(nn),l,h,xyz(d))
        plan,reason=self.calculate_group(m,self.group,hosts or [self.host],set(),self.cfg)
        self.assertIsNone(reason)
        return plan
    def test_diameter_reduction_recalculates_rect_to_round(self):
        a=self.calculate(75);b=self.calculate(63)
        self.assertEqual(a['shape'],'rect');self.assertEqual(b['shape'],'round')
        self.assertAlmostEqual(b['diameter']*304.8,127)
    def test_diameter_increase_recalculates_round_to_rect(self):
        self.assertEqual(self.calculate(63)['shape'],'round')
        self.assertEqual(self.calculate(75)['shape'],'rect')
    def test_reason_includes_comparable_diameters_and_host(self):
        plan=self.calculate(75);reason=plan['shape_reason']
        for text in ['host=CURRENT:wall','D_e=75.00','D_0=125.00','core=127.00','D_required=',
                     'depth=200.00','angle=3.0000']:
            self.assertIn(text,reason)
        self.assertGreater(plan['round_check']['required_diameter'],plan['round_check']['selected_core'])
    def test_empty_circle_is_distinguished_from_fit_failure(self):
        self.empty_circle=True;plan=self.calculate(63)
        self.assertEqual(plan['shape'],'rect')
        self.assertIn('Circular volume has no construction intersection',plan['shape_reason'])
        self.assertIn('circular_hits=0',plan['shape_reason'])
        self.assertIn('probe_center_mm=',plan['shape_reason'])
        self.assertEqual(plan['round_check']['depth_source'],'rectangular_probe')
    def test_successful_circle_records_final_depth(self):
        p=self.calculate(63)
        self.assertEqual(p['round_check']['depth_source'],'circular_intersection')
        self.assertGreater(p['round_check']['hit_count'],0)
        self.assertLessEqual(p['round_check']['required_diameter'],p['diameter'])

    def test_moving_base_host_recalculates_insertion_from_new_geometry(self):
        self.host.support=lambda i:self.layer['low']
        before=self.calculate(63)
        shift=200/304.8
        moved=NS(nr=(shift,shift+self.thickness))
        self.layer.update(low=shift,high=shift+self.thickness,solids=[moved])
        self.group=(shift,shift+self.thickness,[dict(host=self.host,layer=self.layer,hits=[moved])])
        after=self.calculate(63)
        self.assertEqual(before['participants'][0]['uid'],after['participants'][0]['uid'])
        self.assertAlmostEqual((after['insertion'].Y-before['insertion'].Y)*304.8,200)
        self.assertAlmostEqual((after['insertion'].X-before['insertion'].X)*304.8,
                               200*math.tan(math.radians(3)))

    def test_adding_wall_at_50mm_gap_recalculates_group_and_changes_base(self):
        before=self.calculate(63)
        start=self.thickness+50/304.8
        end=start+300/304.8
        solid=NS(nr=(start,end))
        layer=dict(index=0,width=300/304.8,low=start,high=end,solids=[solid])
        added=NS(key='CURRENT:added-wall',normal=self.normal,base_index=0,
            has_structure_layer=True,is_structural=True,wall=True,definition='a'*64,source=NS(key='CURRENT'),
            element=NS(UniqueId='added-wall'),layer_data=[layer],bounds=None,support=lambda i:start)
        members=self.group[2]+[dict(host=added,layer=layer,hits=[solid])]
        self.group=(0,end,members)
        after=self.calculate(63,[self.host,added])
        self.assertEqual(after['host'].key,'CURRENT:added-wall')
        self.assertAlmostEqual(after['depth']*304.8,550)
        self.assertEqual(len(after['participants']),2)
        old_payload=sync.desired_payload(before,'symbol','old-run',
                         '3954b5b0-1d18-42ef-bcc6-785b45229da6')
        new_payload=sync.desired_payload(after,'symbol')
        old_record=dict(element=NS(Id=10),payload=old_payload,actual=old_payload['state'])
        result=sync.reconcile([old_record],[dict(plan=after,payload=new_payload)],
                               lambda p:None,.1/304.8,.0001)
        self.assertEqual([r['kind'] for r in result],['create','delete'])
        self.assertNotEqual(result[0]['payload']['opening_guid'],old_payload['opening_guid'])

    def test_checked_base_layer_precedes_unchecked_thicker_layer_in_plan(self):
        self.host.is_structural=False
        start=self.thickness+50/304.8;end=start+50/304.8
        solid=NS(nr=(start,end));layer=dict(index=0,width=50/304.8,low=start,high=end,solids=[solid])
        thin=NS(key='CURRENT:structural-thin',normal=self.normal,base_index=0,is_structural=True,
            has_structure_layer=True,wall=True,definition='b'*64,source=NS(key='CURRENT'),
            element=NS(UniqueId='structural-thin'),layer_data=[layer],bounds=None,support=lambda i:start)
        self.group=(0,end,self.group[2]+[dict(host=thin,layer=layer,hits=[solid])])
        plan=self.calculate(63,[self.host,thin])
        self.assertEqual(plan['host'].key,thin.key)
        self.assertTrue(plan['base_selection']['structural'])
        self.assertAlmostEqual(plan['base_selection']['width']*304.8,50)

    def attach_adjacent(self,structural=False,width_mm=100,gap_mm=50):
        start=self.thickness+gap_mm/304.8;end=start+width_mm/304.8
        solid=NS(nr=(start,end));layer=dict(index=0,width=width_mm/304.8,low=start,high=end,solids=[solid])
        other=NS(key='CURRENT:adjacent',normal=self.normal,base_index=0 if structural else None,
            is_structural=structural,wall=True,definition='b'*64,source=NS(key='CURRENT'),
            element=NS(UniqueId='adjacent'),layer_data=[layer],bounds=None,support=lambda i:start)
        self.group=(0,end,self.group[2]+[dict(host=other,layer=layer,hits=[solid])])
        return other
    def test_through_all_one_includes_adjacent_nonstructural_instance(self):
        self.cfg=self.cfg._replace(through_all=True)
        other=self.attach_adjacent(False)
        plan=self.calculate(63,[self.host,other])
        self.assertEqual(plan['host'].key,self.host.key)
        self.assertAlmostEqual(plan['depth']*304.8,350)
        self.assertEqual(len(plan['participants']),2)
    def test_through_all_zero_excludes_adjacent_nonstructural_instance(self):
        self.cfg=self.cfg._replace(through_all=False)
        other=self.attach_adjacent(False)
        plan=self.calculate(63,[self.host,other])
        self.assertAlmostEqual(plan['depth']*304.8,200)
        self.assertEqual(len(plan['participants']),1)
    def test_through_all_zero_uses_only_thickest_structural_instance(self):
        self.cfg=self.cfg._replace(through_all=False)
        other=self.attach_adjacent(True,width_mm=300)
        plan=self.calculate(63,[self.host,other])
        self.assertEqual(plan['host'].key,other.key)
        self.assertAlmostEqual(plan['depth']*304.8,300)
        self.assertEqual(len(plan['participants']),1)
    def test_no_checked_structure_layer_never_produces_opening(self):
        self.host.is_structural=False;self.host.base_index=None
        for through in (False,True):
            cfg=self.cfg._replace(through_all=through)
            plan,reason=self.calculate_group(None,self.group,[self.host],set(),cfg)
            self.assertIsNone(plan);self.assertIn('Structural Material=Yes',reason)
    def test_equal_thickness_base_closest_to_project_base_point(self):
        other=self.attach_adjacent(True,width_mm=200)
        # Project Base Point lies near the second passage, not near global zero.
        self.host.reference_point=other.reference_point=(0,350/304.8,0)
        plan=self.calculate(63,[self.host,other])
        self.assertEqual(plan['host'].key,other.key)
    def test_pbp_choice_same_with_reversed_axis_direction(self):
        # The anchor is an infinite-line/median-plane intersection, independent of end order.
        root=os.path.join(os.path.dirname(__file__),'..','HDL Openings.extension','lib','hdl_openings','engine.py')
        with open(root) as f:tree=ast.parse(f.read())
        tree.body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='passage_anchor']
        ns={'EPS':1e-7};exec(compile(tree,root,'exec'),ns)
        forward=NS(origin=V(0,0,0),axis=V(0,1,0))
        reverse=NS(origin=V(0,1,0),axis=V(0,-1,0))
        a=ns['passage_anchor'](forward,self.host,self.layer)
        b=ns['passage_anchor'](reverse,self.host,self.layer)
        self.assertEqual(xyz(a),xyz(b))

    def checked_100mm_with_finish_20mm(self):
        depth=100/304.8;total=120/304.8
        base_solid=NS(nr=(0,depth));finish_solid=NS(nr=(depth,total))
        base=dict(index=1,width=depth,low=0.,high=depth,solids=[base_solid],function_structure=True,structural_material=True)
        finish=dict(index=0,width=20/304.8,low=depth,high=total,solids=[finish_solid],function_structure=False,structural_material=False)
        self.host.base_index=1;self.host.is_structural=True;self.host.layer_data=[finish,base]
        self.host.support=lambda i:self.host.layer_data[i]['high']
        self.layer=base
        self.group=(0,total,[dict(host=self.host,layer=finish,hits=[finish_solid]),dict(host=self.host,layer=base,hits=[base_solid])])
    def test_through_zero_only_checked_100mm_not_120mm_wall(self):
        self.checked_100mm_with_finish_20mm();self.cfg=self.cfg._replace(through_all=False)
        plan=self.calculate(63)
        self.assertEqual(plan['layer'],1);self.assertAlmostEqual(plan['depth']*304.8,100)
        self.assertEqual(len(plan['participants']),1)
        self.assertTrue(plan['participants'][0]['function_structure'])
        self.assertTrue(plan['participants'][0]['structural_material'])
    def test_through_one_includes_finish_and_checked_layer(self):
        self.checked_100mm_with_finish_20mm();self.cfg=self.cfg._replace(through_all=True)
        plan=self.calculate(63)
        self.assertAlmostEqual(plan['depth']*304.8,120);self.assertEqual(len(plan['participants']),2)

if __name__=='__main__':unittest.main()
