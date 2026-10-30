import os
import sys
import unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'HDL Openings.extension', 'lib'))
from hdl_openings.math_core import insertion_coordinates


class InsertionTests(unittest.TestCase):
    def test_wall_bottom_height_and_start_depth(self):
        self.assertEqual(insertion_coordinates((-250, 250), (1000, 1500), (10, 210), True),
                         (0, 1000, 10))

    def test_floor_top_depth_and_section_center(self):
        self.assertEqual(insertion_coordinates((100, 600), (200, 700), (-200, 0), False),
                         (350, 450, 0))

    def test_wall_reconstructs_full_geometry(self):
        xr, yr, nr = (-50, 250), (800, 1300), (-600, -400)
        x, y, n = insertion_coordinates(xr, yr, nr, True)
        self.assertEqual((x - 150, x + 150), xr)
        self.assertEqual((y, y + 500), yr)
        self.assertEqual((n, n + 200), nr)

    def test_floor_reconstructs_full_geometry(self):
        xr, yr, nr = (30, 330), (-150, 350), (800, 1050)
        x, y, n = insertion_coordinates(xr, yr, nr, False)
        self.assertEqual((x - 150, x + 150), xr)
        self.assertEqual((y - 250, y + 250), yr)
        self.assertEqual((n - 250, n), nr)

    def test_degenerate_range_rejected(self):
        with self.assertRaises(ValueError):
            insertion_coordinates((0, 1), (2, 2), (0, 3), True)

if __name__ == '__main__':
    unittest.main()
