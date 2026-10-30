"""Execute the production MEP adapter with stand-ins for native connector/insulation APIs."""
import ast
import os
import unittest
from types import SimpleNamespace as NS

class V:
    def __init__(self,x,y,z):self.X=x;self.Y=y;self.Z=z
    def Normalize(self):return self
    def DotProduct(self,b):return self.X*b.X+self.Y*b.Y+self.Z*b.Z
    def DistanceTo(self,b):return ((self.X-b.X)**2+(self.Y-b.Y)**2+(self.Z-b.Z)**2)**.5
class Line:
    Direction=V(0,0,1);Length=10
    def GetEndPoint(self,index):return V(0,0,index*10)
class LocationCurve:
    Curve=Line()
class Base:
    def __init__(self,source,element):
        self.source=source;self.element=element;self.key='mep';self.solids=['body'];self.bounds=None

path=os.path.join(os.path.dirname(__file__),'..','HDL Openings.extension','lib','hdl_openings','model.py')
with open(path) as f:tree=ast.parse(f.read())
tree.body=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Mep']

class InsulationTests(unittest.TestCase):
    def make(self,category=1,shape='round',thickness=.1,extra=True):
        calls=[]
        insulation=NS(Thickness=thickness)
        doc=NS(GetElement=lambda eid:insulation)
        def ids(document,eid):
            calls.append((document,eid))
            return [2] if thickness else []
        db=NS(LocationCurve=LocationCurve,Line=Line,
              BuiltInCategory=NS(OST_PipeCurves=1,OST_Conduit=2,OST_DuctCurves=3),
              ConnectorType=NS(End='end'),ConnectorProfileType=NS(Round='round',Rectangular='rect',Oval='oval'),
              BuiltInParameter=NS(RBS_PIPE_OUTER_DIAMETER='pipeOD',RBS_CONDUIT_OUTER_DIAM_PARAM='conduitOD'),
              InsulationLiningBase=NS(GetInsulationIds=ids))
        ns={'ModelElement':Base,'DB':db,'id_value':lambda eid:eid,
            'geo':NS(UnsupportedGeometry=ValueError,solids=lambda e,t:['insulation'] if extra else [],
                     bbox=lambda solids:list(solids))}
        exec(compile(tree,path,'exec'),ns)
        connector=NS(ConnectorType='end',Origin=V(0,0,0),Shape=shape,Radius=.25,Width=2.,Height=1.,
                     CoordinateSystem=NS(BasisX=V(1,0,0),BasisY=V(0,1,0)))
        element=NS(Location=LocationCurve(),Id=42,Category=NS(Id=category),
                   ConnectorManager=NS(Connectors=[connector]),get_Parameter=lambda p:NS(AsDouble=lambda:1.))
        source=NS(doc=doc,transform=NS(OfVector=lambda v:v,OfPoint=lambda v:v))
        result=ns['Mep'](source,element)
        return result,calls,doc
    def test_pipe_actual_od_not_nominal_connector(self):
        mep,calls,doc=self.make()
        self.assertAlmostEqual(mep.hw,.6)
        self.assertEqual(mep.solids,['body','insulation'])
        self.assertTrue(mep.round_eligible)
        self.assertIs(calls[0][0],doc)
    def test_rect_duct_insulation_and_rectangular_only(self):
        mep,_,_=self.make(category=3,shape='rect')
        self.assertAlmostEqual(mep.hw,1.1);self.assertAlmostEqual(mep.hh,.6)
        self.assertFalse(mep.round_eligible)
    def test_oval_duct_insulation(self):
        mep,_,_=self.make(category=3,shape='oval')
        self.assertEqual(mep.circular,'oval');self.assertAlmostEqual(mep.hh,.6)
    def test_round_duct_is_not_round_opening(self):
        mep,_,_=self.make(category=3)
        self.assertTrue(mep.circular);self.assertFalse(mep.round_eligible)
    def test_bare_conduit_actual_od(self):
        mep,calls,_=self.make(category=2)
        self.assertEqual(calls,[]);self.assertAlmostEqual(mep.hw,.5)
    def test_missing_insulation_geometry_is_error(self):
        with self.assertRaises(ValueError):self.make(extra=False)

if __name__=='__main__':unittest.main()
