"""Verify the actual void-volume conventions, including transformed openings."""
import ast
import os
import math
import unittest
from types import SimpleNamespace as NS


class V:
    def __init__(self,x,y,z):self.X,self.Y,self.Z=x,y,z
    def DotProduct(self,b):return self.X*b.X+self.Y*b.Y+self.Z*b.Z
    def Normalize(self):
        n=math.sqrt(self.DotProduct(self));return V(self.X/n,self.Y/n,self.Z/n)


class Point:
    def __init__(self,p):self.Point=p


class VolumeTests(unittest.TestCase):
    def setUp(self):
        path=os.path.join(os.path.dirname(__file__),'..','HDL Openings.extension','lib','hdl_openings','mep_geometry.py')
        with open(path) as f:tree=ast.parse(f.read())
        tree.body=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Opening']
        self.captured={}
        def prism(x,y,n,xr,yr,nr):self.captured.update(xr=xr,yr=yr,nr=nr);return object()
        def cylinder(x,y,n,origin,diameter,nr):self.captured.update(origin=origin,diameter=diameter,nr=nr);return object()
        ns=dict(DB=NS(LocationPoint=Point),length=lambda e,n:e.dimensions[n],
                geo=NS(prism=prism,cylinder=cylinder,bbox=lambda s:None))
        exec(compile(tree,path,'exec'),ns);self.Opening=ns['Opening']
        self.families=NS(rect_wall='rw',round_wall='cw',rect_floor='rf',round_floor='cf')
    def opening(self,name,rotated=False):
        tf=NS(BasisX=V(0,1,0) if rotated else V(1,0,0),
              BasisY=V(-1,0,0) if rotated else V(0,1,0),BasisZ=V(0,0,1))
        e=NS(Symbol=NS(Family=NS(Name=name)),Location=Point(V(10,20,30)),
             GetTransform=lambda:tf,dimensions=dict(Depth=2,Width=4,Height=6,Diameter=3))
        return self.Opening(e,self.families)
    def test_rect_wall_starts_at_bottom(self):
        self.opening('rw');self.assertEqual(self.captured,dict(xr=(8,12),yr=(30,36),nr=(20,22)))
    def test_floor_depth_is_negative_local_z(self):
        self.opening('rf');self.assertEqual(self.captured,dict(xr=(8,12),yr=(17,23),nr=(28,30)))
    def test_round_wall(self):
        self.opening('cw');self.assertEqual(self.captured['nr'],(20,22));self.assertEqual(self.captured['diameter'],3)
    def test_round_floor(self):
        self.opening('cf');self.assertEqual(self.captured['nr'],(28,30))
    def test_rotated_wall(self):
        self.opening('rw',True);self.assertEqual(self.captured,dict(xr=(18,22),yr=(30,36),nr=(-10,-8)))
    def test_rotated_floor(self):
        self.opening('rf',True);self.assertEqual(self.captured,dict(xr=(18,22),yr=(-13,-7),nr=(28,30)))


if __name__=='__main__':unittest.main()
