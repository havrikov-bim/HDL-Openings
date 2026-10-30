import ast
import math
import os
import sys
import unittest
from types import SimpleNamespace as NS
sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..','HDL Openings.extension','lib'))
from hdl_openings.section_math import layer_normal_interval
from hdl_openings.math_core import merge_intervals

class V:
    def __init__(self,x,y,z):self.X=x;self.Y=y;self.Z=z
    def Multiply(self,k):return V(self.X*k,self.Y*k,self.Z*k)
    def Add(self,b):return V(self.X+b.X,self.Y+b.Y,self.Z+b.Z)
    def DotProduct(self,b):return self.X*b.X+self.Y*b.Y+self.Z*b.Z

path=os.path.join(os.path.dirname(__file__),'..','HDL Openings.extension','lib','hdl_openings','engine.py')
with open(path) as f:tree=ast.parse(f.read())
tree.body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('xyz','passage_anchor','layer_range','base_rank','detect')]
ns={'merge_intervals':merge_intervals,'layer_normal_interval':layer_normal_interval,
    'GAP':50.,'EPS':1e-7,'geo':NS(overlaps=lambda a,b:True,intersect=lambda a,b:object())}
exec(compile(tree,path,'exec'),ns)

class NormalGapTests(unittest.TestCase):
    def groups(self,angle,gap,reverse=False):
        c=math.cos(math.radians(angle));ss=math.sin(math.radians(angle))
        mep=NS(origin=V(0,0,-100),axis=V(ss,0,c),bounds=None,solids=[object()])
        hosts=[]
        for i,(lo,hi) in enumerate(((0,200),(200+gap,400+gap))):
            n=V(0,0,1)
            if reverse and i==1:n=V(0,0,-1);lo,hi=-hi,-lo
            layer=dict(index=0,low=lo,high=hi,width=200,solids=[object()])
            hosts.append(NS(normal=n,base_index=0,has_structure_layer=True,
                            key=str(i),bounds=None,layer_data=[layer]))
        return ns['detect'](mep,hosts,NS(gap=50.))
    def test_50mm_combines_for_multiple_angles(self):
        for angle in (0,15,30,45,60,75):
            self.assertEqual(len(self.groups(angle,50)),1,angle)
    def test_100mm_separates_for_multiple_angles(self):
        for angle in (0,30,60,75):self.assertEqual(len(self.groups(angle,100)),2,angle)
    def test_just_above_threshold_separates(self):
        self.assertEqual(len(self.groups(45,50.001)),2)
    def test_opposite_normals_same_result(self):
        self.assertEqual(len(self.groups(45,50,True)),1)
        self.assertEqual(len(self.groups(45,100,True)),2)
    def test_nonparallel_normal_not_silently_projected(self):
        with self.assertRaises(ValueError):
            layer_normal_interval((0,0,0),(0,0,1),(0,0,1),0,1,(1,0,0))

if __name__=='__main__':unittest.main()
