import math
import os
import sys
import unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'HDL Openings.extension', 'lib'))
from hdl_openings.math_core import merge_intervals, trig_range, rect_size


class MathTests(unittest.TestCase):
    def test_transitive_and_nested_intervals(self):
        self.assertEqual(merge_intervals([(0, 10, 'a'), (2, 3, 'b'), (11, 12, 'c')], 1),
                         [[0, 12, ['a', 'b', 'c']]])

    def test_gap_boundary_and_separation(self):
        self.assertEqual(len(merge_intervals([(0, 1, 1), (3, 4, 2)], 2)), 1)
        self.assertEqual(len(merge_intervals([(0, 1, 1), (3.01, 4, 2)], 2)), 2)

    def test_full_ellipse_extrema(self):
        lo, hi = trig_range(7, 3, 4, 0, 2 * math.pi)
        self.assertAlmostEqual(lo, 2)
        self.assertAlmostEqual(hi, 12)

    def test_trimmed_arc_does_not_use_full_circle(self):
        lo, hi = trig_range(0, 1, 0, math.pi / 4, math.pi / 3)
        self.assertAlmostEqual(lo, .5)
        self.assertAlmostEqual(hi, math.sqrt(.5))

    def test_wrapped_parameters(self):
        lo, hi = trig_range(0, 1, 0, 1.5 * math.pi, 2.5 * math.pi)
        self.assertAlmostEqual(hi, 1)
        self.assertAlmostEqual(lo, 0)

    def test_clearance_is_on_both_sides(self):
        self.assertEqual(rect_size((10, 30), (-10, 30), 25), (70, 90))

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            merge_intervals([(3, 2, None)], 1)
        with self.assertRaises(ValueError):
            rect_size((0, 1), (0, 1), -1)

if __name__ == '__main__':
    unittest.main()
