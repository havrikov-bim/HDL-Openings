"""The real Host constructor must never request type layers or materials."""
import ast
import hashlib
import json
import os
import unittest
from types import SimpleNamespace as NS
PATH=os.path.join(os.path.dirname(__file__),'..','HDL Openings.extension','lib','hdl_openings','model.py')
with open(PATH) as f:tree=ast.parse(f.read())
tree.body=[n for n in tree.body if (isinstance(n,ast.ClassDef) and n.name=='Host') or
           (isinstance(n,ast.FunctionDef) and n.name=='eligible_layer_indices')]

class V:
    def __init__(self,x,y,z):self.X=x;self.Y=y;self.Z=z
    def Normalize(self):return self
    def Negate(self):return V(-self.X,-self.Y,-self.Z)
    def DotProduct(self,b):return self.X*b.X+self.Y*b.Y+self.Z*b.Z
class Line:pass
class Wall:
    Orientation=V(0,1,0);Location=NS(Curve=Line())
    def __init__(self,flag):self.flag=flag
    def get_Parameter(self,key):return NS(AsInteger=lambda:self.flag) if key=='wall' else None
    def GetTypeId(self):raise AssertionError('Types and compound structure must not be read')
class Floor:
    def __init__(self,flag):self.flag=flag
    def get_Parameter(self,key):return NS(AsInteger=lambda:self.flag) if key=='floor' else None
    def GetTypeId(self):raise AssertionError('Types must not be read')
class Face:
    def __init__(self,normal,z):self.FaceNormal=normal;self.Origin=V(0,0,z);self.Area=10
class Base:
    def __init__(self,source,element):
        self.source=source;self.element=element;self.key='host'
        self.solids=[NS(Faces=[Face(V(0,0,-1),0),Face(V(0,0,1),120/304.8)])];self.bounds=[(0,1)]*3

class CompoundHostTests(unittest.TestCase):
    def host(self,element,checked=1,functions=('Finish1','Structure')):
        items=[NS(Function=functions[0],Width=20/304.8),NS(Function=functions[1],Width=100/304.8)]
        cs=NS(StructuralMaterialIndex=checked,VariableLayerIndex=-1,
              IsVerticallyHomogeneous=lambda:True,GetLayers=lambda:items)
        element.GetTypeId=lambda:1
        # The instance Structural checkbox must not be read.
        element.get_Parameter=lambda key:(_ for _ in ()).throw(AssertionError('Instance flag must be ignored'))
        def clip(solid,normal,low,high):return NS(nr=(low,high)) if high>low else None
        geo=NS(combined_range=lambda solids,n:(0.,120/304.8),UnsupportedGeometry=ValueError,clip=clip)
        ns=dict(DB=NS(Wall=Wall,Line=Line,PlanarFace=Face,
                     MaterialFunctionAssignment=NS(Structure='Structure')),
                ModelElement=Base,geo=geo,EPS=1e-7,MM=1/304.8,hashlib=hashlib,json=json)
        exec(compile(tree,PATH,'exec'),ns)
        source=NS(transform=NS(OfVector=lambda v:v),reference_point=(10,20,30),
                  doc=NS(GetElement=lambda eid:NS(GetCompoundStructure=lambda:cs)))
        return ns['Host'](source,element)
    def test_wall_100mm_structure_checked_plus_20mm_finish(self):
        host=self.host(Wall(0))
        self.assertEqual(host.base_index,1);self.assertTrue(host.is_structural)
        self.assertEqual(len(host.layer_data),2)
        self.assertAlmostEqual(host.layer_data[1]['width']*304.8,100)
        self.assertAlmostEqual(host.layer_data[1]['low'],0)
        self.assertAlmostEqual(host.layer_data[1]['high']*304.8,100)
    def test_instance_structural_no_does_not_disqualify_checked_layer(self):
        self.assertEqual(self.host(Wall(0)).base_index,1)
    def test_instance_structural_yes_does_not_replace_missing_layer_checkbox(self):
        self.assertIsNone(self.host(Wall(1),checked=-1).base_index)
    def test_wrong_function_cannot_be_base_even_if_checked(self):
        self.assertIsNone(self.host(Wall(1),checked=0).base_index)
    def test_floor_uses_same_layer_eligibility(self):self.assertEqual(self.host(Floor(0)).base_index,1)
    def test_roof_uses_same_layer_rule_without_native_structural_flag(self):
        roof=NS()
        self.assertEqual(self.host(roof).base_index,1)
    def test_reference_point_unchanged(self):self.assertEqual(self.host(Wall(0)).reference_point,(10,20,30))
    def test_checked_layer_support_is_its_surface_not_outer_finish(self):
        self.assertAlmostEqual(self.host(Wall(0)).support(1)*304.8,100)
    def test_roofs_are_collected_again(self):
        with open(PATH) as f:module=ast.parse(f.read())
        module.body=[n for n in module.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='HOST_CATEGORIES' for t in n.targets)]
        ns=dict(DB=NS(BuiltInCategory=NS(OST_Walls=1,OST_Floors=2,OST_Roofs=3)))
        exec(compile(module,PATH,'exec'),ns);self.assertEqual(ns['HOST_CATEGORIES'],(1,2,3))

class SourceReferenceTests(unittest.TestCase):
    def load(self,point):
        with open(PATH) as f:module=ast.parse(f.read())
        module.body=[n for n in module.body if (isinstance(n,ast.ClassDef) and n.name=='Source') or
                     (isinstance(n,ast.FunctionDef) and n.name=='sources')]
        self.calls=[]
        def get_point(doc):self.calls.append(doc);return point
        link=NS(UniqueId='link',GetLinkDocument=lambda:'linked-doc',GetTotalTransform=lambda:'transform')
        class Collector:
            def __init__(self,doc):pass
            def OfClass(self,cls):return [link]
        db=NS(BasePoint=NS(GetProjectBasePoint=get_point),Transform=NS(Identity='identity'),
              FilteredElementCollector=Collector,RevitLinkInstance=object)
        ns=dict(DB=db,geo=NS(UnsupportedGeometry=ValueError));exec(compile(module,PATH,'exec'),ns)
        return ns['sources']
    def test_current_and_linked_hosts_use_current_project_base_point(self):
        sources=self.load(NS(Position=V(10,20,30)))('current-doc')
        self.assertEqual(self.calls,['current-doc'])
        self.assertEqual([s.reference_point for s in sources],[(10,20,30),(10,20,30)])
        self.assertEqual([s.key for s in sources],['CURRENT','link'])
    def test_missing_project_base_point_blocks_without_origin_substitution(self):
        read=self.load(None)
        with self.assertRaises(ValueError):read('current-doc')

if __name__=='__main__':unittest.main()
