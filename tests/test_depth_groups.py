import os
import sys
import unittest
sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..','HDL Openings.extension','lib'))
from hdl_openings.math_core import merge_intervals,may_extend_group
from hdl_openings.section_math import axis_interval,passage_interval
import math

class DepthGroupTests(unittest.TestCase):
    def test_separate_structural_slabs_remain_separate(self):
        groups=merge_intervals([(0,200,'slab1'),(260,460,'slab2')],50)
        self.assertEqual(len(groups),2)
        self.assertFalse(may_extend_group(groups[0][:2],(260,460),50,True))
    def test_finish_at_40_can_extend(self):
        self.assertTrue(may_extend_group((0,200),(240,340),50,False))
    def test_finish_at_60_cannot_extend(self):
        self.assertFalse(may_extend_group((0,200),(260,360),50,False))
    def test_other_group_cannot_be_captured_by_wide_probe(self):
        self.assertFalse(may_extend_group((0,200),(195,340),50,True))
    def test_boundary(self):
        self.assertTrue(may_extend_group((0,200),(250,350),50,False))
        self.assertFalse(may_extend_group((0,200),(250.001,350),50,False))
    def test_oblique_large_profile_does_not_close_100mm_gap(self):
        c=math.cos(math.radians(30));a=(math.sin(math.radians(30)),0,c)
        args=((0,0,0),a,2000,(0,0,1))
        first=axis_interval(*(args+(100,300)))
        second=axis_interval(*(args+(400,600)))
        self.assertEqual(len(merge_intervals([(first[0],first[1],1),
                                              (second[0],second[1],2)],50)),2)
        self.assertAlmostEqual(second[0]-first[1],100/c)

if __name__=='__main__':unittest.main()
