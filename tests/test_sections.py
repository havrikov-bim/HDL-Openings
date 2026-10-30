import math
import os
import sys
import unittest
sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..','HDL Openings.extension','lib'))
from hdl_openings.section_math import swept_range, passage_interval, axis_trace_length

O=(0,0,0);Z=(0,0,1);X=(1,0,0);Y=(0,1,0)

class SectionTests(unittest.TestCase):
    def test_rect_normal(self):
        self.assertEqual(swept_range(O,Z,X,Y,2,3,False,Z,0,10,X),(-2,2))
        self.assertEqual(swept_range(O,Z,X,Y,2,3,False,Z,0,10,Y),(-3,3))
    def test_round_normal(self):
        self.assertEqual(swept_range(O,Z,X,Y,2,2,True,Z,0,10,X),(-2,2))
    def test_rect_twist(self):
        c=math.sqrt(.5)
        lo,hi=swept_range(O,Z,(c,c,0),(-c,c,0),2,3,False,Z,0,10,X)
        self.assertAlmostEqual(hi,5*c);self.assertAlmostEqual(lo,-5*c)
    def test_round_twist_invariant(self):
        c=math.sqrt(.5)
        self.assertAlmostEqual(swept_range(O,Z,(c,c,0),(-c,c,0),2,2,True,Z,0,10,X)[1],2)
    def test_oblique_round_ellipse_and_axis_drift(self):
        c=math.sqrt(.5)
        lo,hi=swept_range(O,(c,0,c),(c,0,-c),Y,2,2,True,Z,0,10,X)
        self.assertAlmostEqual(lo,-2/c);self.assertAlmostEqual(hi,10+2/c)
    def test_oblique_normal_extent_equals_slab(self):
        c=math.sqrt(.5)
        self.assertEqual(swept_range(O,(c,0,c),(c,0,-c),Y,2,2,True,Z,4,10,Z),(4,10))
    def test_reverse_direction(self):
        self.assertEqual(passage_interval((0,0,20),(0,0,-1),30,X,Y,2,3,False,Z,0,10),(10,20))
    def test_finite_end(self):
        self.assertEqual(passage_interval(O,Z,5,X,Y,2,3,False,Z,4,10),(4,5))
    def test_parallel_rejected(self):
        with self.assertRaises(ValueError):swept_range(O,X,Y,Z,1,1,False,Z,0,10,X)
class AxisTraceTests(unittest.TestCase):
    def test_oblique_large_section_does_not_reject_axis(self):
        c=math.cos(math.radians(30)); a=(math.sin(math.radians(30)),0,c)
        trace=axis_trace_length(O,a,1000,Z,100,300)
        self.assertAlmostEqual(trace,200/c)
        self.assertLess(trace,1.5*200)
        full=passage_interval(O,a,1000,(c,0,-.5),Y,300,100,False,Z,100,300)
        self.assertGreater(full[1]-full[0],1.5*200)
    def test_axis_limit_still_rejects_steep_angle(self):
        a=(math.sin(math.radians(60)),0,math.cos(math.radians(60)))
        self.assertAlmostEqual(axis_trace_length(O,a,1000,Z,100,300),400)
    def test_reverse_axis(self):
        self.assertEqual(axis_trace_length((0,0,20),(0,0,-1),30,Z,0,10),10)
    def test_partial_axis(self):
        self.assertEqual(axis_trace_length(O,Z,5,Z,4,10),1)
    def test_axis_outside_layer(self):
        self.assertEqual(axis_trace_length(O,Z,3,Z,4,10),0)

if __name__=='__main__':unittest.main()
