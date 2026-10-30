import math
import os
import sys
import unittest
sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..','HDL Openings.extension','lib'))
from hdl_openings.opening_math import ceil_step,choose_round
from hdl_openings.section_math import section_support
CORES=[25.4,31.75,38.1,50.8,76.2,101.6,127,152.4,203.2,254,304.8]

class OpeningMathTests(unittest.TestCase):
    def test_round_up(self):
        for x,y in [(300,300),(301,350),(312,350),(349,350),(350,350)]:self.assertEqual(ceil_step(x,50),y)
    def test_alternate_step(self):self.assertEqual(ceil_step(312,25),325)
    def test_units_conversion_rounding(self):self.assertAlmostEqual(ceil_step(300/304.8,50/304.8)*304.8,300)
    def test_zero_step_rejected(self):
        with self.assertRaises(ValueError):ceil_step(100,0)
    def test_choose_larger_after_clearance(self):
        self.assertEqual(choose_round(63,1,200,25,CORES,1000)[0],127)
    def test_exact_size_selects_next_core(self):
        self.assertEqual(choose_round(50.8,1,200,0,CORES,1000)[0],76.2)
    def test_depth_boundary(self):
        self.assertEqual(choose_round(63,1,1000,25,CORES,1000)[0],127)
        self.assertIsNone(choose_round(63,1,1000.01,25,CORES,1000)[0])
    def test_angle_and_depth_change_fit(self):
        c=math.cos(math.radians(3))
        self.assertEqual(choose_round(63,c,100,25,CORES,1000)[0],127)
        self.assertIsNone(choose_round(63,c,1000,25,CORES,1000)[0])
    def test_never_upsize_failed_core(self):
        self.assertIsNone(choose_round(63,math.cos(math.radians(15)),300,25,CORES,1000)[0])
    def test_maximum_catalogue_exceeded(self):self.assertIsNone(choose_round(400,1,200,25,CORES,1000)[0])
    def test_flat_oval_support(self):
        self.assertEqual(section_support((1,0,0),(1,0,0),(0,1,0),200,100,'oval'),200)
        self.assertEqual(section_support((0,1,0),(1,0,0),(0,1,0),200,100,'oval'),100)
        expected=100*math.sqrt(.5)+100
        self.assertAlmostEqual(section_support((math.sqrt(.5),math.sqrt(.5),0),(1,0,0),(0,1,0),200,100,'oval'),expected)
    def test_oval_insulation_minkowski_offset(self):
        d=(.6,.8,0);u=(1,0,0);v=(0,1,0)
        bare=section_support(d,u,v,200,100,'oval')
        insulated=section_support(d,u,v,225,125,'oval')
        self.assertAlmostEqual(insulated-bare,25)

if __name__=='__main__':unittest.main()
