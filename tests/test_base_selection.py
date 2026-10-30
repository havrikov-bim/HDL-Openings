import ast
import itertools
import os
import unittest
from types import SimpleNamespace as NS
ROOT=os.path.join(os.path.dirname(__file__),'..','HDL Openings.extension','lib','hdl_openings')

def function(name,file,namespace):
    with open(os.path.join(ROOT,file)) as f:tree=ast.parse(f.read())
    tree.body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name]
    exec(compile(tree,file,'exec'),namespace)
    return namespace[name]

class V:
    def __init__(self,x,y,z):self.X=x;self.Y=y;self.Z=z
    def Multiply(self,k):return V(self.X*k,self.Y*k,self.Z*k)

class BaseSelectionTests(unittest.TestCase):
    def setUp(self):self.rank=function('base_rank','engine.py',{'xyz':lambda v:(v.X,v.Y,v.Z)})
    def candidate(self,uid,width,structural=True,position=0,reference=(0,0,0),normal=None):
        layer=dict(index=0,width=width,low=position-width/2,high=position+width/2)
        host=NS(key=uid,base_index=0 if structural else None,is_structural=structural,
                normal=normal or V(0,1,0),reference_point=reference)
        return dict(host=host,layer=layer)
    def winner(self,*candidates):
        eligible=[p for p in candidates if not self.rank(p)[0]]
        return min(eligible,key=self.rank)['host'].key if eligible else None
    def test_no_structural_flag_means_no_base(self):
        self.assertIsNone(self.winner(self.candidate('A',300,False)))
    def test_nonstructural_thicker_never_becomes_base(self):
        self.assertEqual(self.winner(self.candidate('yes',100),self.candidate('no',300,False)),'yes')
    def test_thickest_structural_instance_wins(self):
        self.assertEqual(self.winner(self.candidate('thin',100),self.candidate('thick',200)),'thick')
    def test_project_base_point_distance_not_min_global_coordinate(self):
        a=self.candidate('near',200,position=900,reference=(0,1000,0))
        b=self.candidate('far',200,position=100,reference=(0,1000,0))
        for order in itertools.permutations([a,b]):self.assertEqual(self.winner(*order),'near')
    def test_nearest_distance_not_min_negative_coordinate(self):
        a=self.candidate('far',200,position=-500);b=self.candidate('near',200,position=100)
        self.assertEqual(self.winner(a,b),'near')
    def test_reverse_normal_keeps_same_physical_distance(self):
        a=self.candidate('far',200,position=500)
        b=self.candidate('near',200,position=-100,normal=V(0,-1,0))
        self.assertEqual(self.winner(a,b),'near')
    def test_thickness_precedes_distance(self):
        self.assertEqual(self.winner(self.candidate('thin-near',100,position=0),
                                     self.candidate('thick-far',200,position=1000)),'thick-far')
    def test_nonbase_slot_not_eligible(self):
        a=self.candidate('wrong',300);a['layer']['index']=1
        self.assertEqual(self.winner(a,self.candidate('base',100)),'base')
    def test_equal_distance_uses_stable_coordinate_tie(self):
        a=self.candidate('plus',200,position=100);b=self.candidate('minus',200,position=-100)
        self.assertEqual(self.winner(a,b),'minus')

class LayerEligibilityTests(unittest.TestCase):
    def setUp(self):
        db=NS(MaterialFunctionAssignment=NS(Structure='Structure'))
        self.read=function('eligible_layer_indices','model.py',dict(DB=db,EPS=1e-7))
    def check(self,function_value,index=0,width=.1):
        return self.read(NS(StructuralMaterialIndex=index),[NS(Function=function_value,Width=width)])
    def test_both_required_flags_accept_layer(self):self.assertEqual(self.check('Structure'),[0])
    def test_function_without_checkbox_rejected(self):self.assertEqual(self.check('Structure',-1),[])
    def test_checkbox_without_function_rejected(self):self.assertEqual(self.check('Finish1'),[])
    def test_invalid_checkbox_index_not_silently_substituted(self):self.assertEqual(self.check('Structure',4),[])
    def test_zero_width_layer_not_base(self):self.assertEqual(self.check('Structure',width=0),[])
    def test_only_checked_structure_layer_is_eligible(self):
        layers=[NS(Function='Structure',Width=.3),NS(Function='Structure',Width=.1)]
        self.assertEqual(self.read(NS(StructuralMaterialIndex=1),layers),[1])

if __name__=='__main__':unittest.main()
