import ast
import os
import unittest
from types import SimpleNamespace as NS

class V:
    def __init__(self,z):self.Z=z
    def Subtract(self,b):return V(self.Z-b.Z)
    def DotProduct(self,b):return self.Z*b.Z
    def Normalize(self):return self
    def Multiply(self,k):return V(self.Z*k)
    def DistanceTo(self,b):return abs(self.Z-b.Z)
class Ref:
    def CreateLinkReference(self,link):return ('linked',link)
class Face:
    FaceNormal=V(1)
    Origin=V(0)
    def Project(self,p):return NS(UVPoint=0,XYZPoint=V(0))
    def IsInside(self,p):return True
class Transform:
    def OfPoint(self,p):return p
    def OfVector(self,p):return p
    @property
    def Inverse(self):return self

class FaceHostTests(unittest.TestCase):
    def setUp(self):
        path=os.path.join(os.path.dirname(__file__),'..','HDL Openings.extension','lib','hdl_openings','face_host.py')
        with open(path) as f:tree=ast.parse(f.read())
        tree.body=[n for n in tree.body if not isinstance(n,(ast.Import,ast.ImportFrom))]
        self.calls=[]
        def refs(which):
            self.calls.append(which)
            return [Ref()]
        self.ns={'DB':NS(PlanarFace=Face,HostObjectUtils=NS(
            GetTopFaces=lambda host:refs('top'),GetBottomFaces=lambda host:refs('bottom')))}
        exec(compile(tree,path,'exec'),self.ns)
    def plan(self,z=0,link=None,variable=-1):
        host=NS(key='host',variable=variable,
                source=NS(transform=Transform(),link=link),
                element=NS(GetGeometryObjectFromReference=lambda ref:Face()))
        return {'host':host,'support':V(z),'normal':V(1)}
    def test_current_model_face_reference(self):
        result=self.ns['resolve'](self.plan())
        self.assertIsInstance(result['reference'],Ref)
        self.assertEqual(set(self.calls),set(['top','bottom']))
    def test_link_reference_conversion(self):
        result=self.ns['resolve'](self.plan(link='link-instance'))
        self.assertEqual(result['reference'],('linked','link-instance'))
    def test_variable_top_uses_bottom(self):
        self.ns['resolve'](self.plan(variable=0))
        self.assertEqual(self.calls[0],'bottom')
    def test_internal_layer_references_native_face_without_changing_support(self):
        plan=self.plan(z=.5)
        result=self.ns['resolve'](plan)
        self.assertEqual(result['point'].Z,0)
        self.assertEqual(result['structural_point'].Z,.5)
        self.assertEqual(result['structural_offset'],.5)
        self.assertIs(plan['support'],result['structural_point'])
    def test_nonparallel_face_is_rejected(self):
        plan=self.plan()
        class WrongFace(Face):
            FaceNormal=V(0)
        plan['host'].element.GetGeometryObjectFromReference=lambda ref:WrongFace()
        with self.assertRaises(self.ns['FaceHostError']):self.ns['resolve'](plan)
    def test_outside_trimmed_patch_is_skipped(self):
        plan=self.plan()
        class Outside(Face):
            def IsInside(self,p):return False
        plan['host'].element.GetGeometryObjectFromReference=lambda ref:Outside()
        with self.assertRaises(self.ns['FaceHostError']):self.ns['resolve'](plan)

    def test_bottom_used_if_top_not_parallel(self):
        plan=self.plan(z=.5)
        top=Ref();bottom=Ref()
        class TopFace(Face):
            FaceNormal=V(0)
        self.ns['DB'].HostObjectUtils.GetTopFaces=lambda host:[top]
        self.ns['DB'].HostObjectUtils.GetBottomFaces=lambda host:[bottom]
        plan['host'].element.GetGeometryObjectFromReference=lambda ref:TopFace() if ref is top else Face()
        result=self.ns['resolve'](plan)
        self.assertEqual(result['reference_side'],'bottom')
        self.assertEqual(result['structural_point'].Z,.5)
    def test_missing_projection_is_skipped(self):
        plan=self.plan(z=.5)
        class NoProjection(Face):
            def Project(self,p):return None
        plan['host'].element.GetGeometryObjectFromReference=lambda ref:NoProjection()
        with self.assertRaises(self.ns['FaceHostError']):self.ns['resolve'](plan)

if __name__=='__main__':unittest.main()
