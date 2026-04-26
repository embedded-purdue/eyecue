import unittest

from contour_gaze_tracker import (
    DEFAULT_PROJECTION_HALF_FOV_DEG,
    map_gaze_angles_to_screen,
)


class GazeProjectionTests(unittest.TestCase):
    def test_zero_angles_map_to_screen_center(self):
        self.assertEqual(map_gaze_angles_to_screen(0, 0, 1000, 800), (500, 400))

    def test_equal_positive_and_negative_angles_map_symmetrically(self):
        center_x = 500
        left = map_gaze_angles_to_screen(-10, 0, 1000, 800)
        right = map_gaze_angles_to_screen(10, 0, 1000, 800)

        self.assertAlmostEqual(center_x - left[0], right[0] - center_x, delta=1)
        self.assertEqual(left[1], 400)
        self.assertEqual(right[1], 400)

    def test_default_projection_is_bounded_for_stable_center_control(self):
        center_x = 500
        moved = map_gaze_angles_to_screen(10, 0, 1000, 800)

        self.assertGreater(DEFAULT_PROJECTION_HALF_FOV_DEG, 45)
        self.assertLess(moved[0] - center_x, 90)

    def test_projection_clamps_extreme_angles(self):
        x, y = map_gaze_angles_to_screen(90, -90, 1000, 800)

        self.assertGreaterEqual(x, 0)
        self.assertLessEqual(x, 999)
        self.assertGreaterEqual(y, 0)
        self.assertLessEqual(y, 799)


if __name__ == "__main__":
    unittest.main()
