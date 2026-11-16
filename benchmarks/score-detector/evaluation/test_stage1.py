import unittest

from score_detector import detect_score_changes


class BaselineContract(unittest.TestCase):
    def test_initial_state(self):
        self.assertEqual(detect_score_changes([(0, 0), (10, 0), (20, 0)]), [])

    def test_one_change(self):
        observations = [(0, 0), (1, 0), (2, 0), (30, 1), (40, 1), (50, 1)]
        self.assertEqual(detect_score_changes(observations), [(30, 0, 1)])

    def test_multi_change(self):
        obs = [(i, score) for i, score in enumerate([0]*3 + [1]*3 + [0]*3 + [2]*3)]
        self.assertEqual(detect_score_changes(obs), [(3, 0, 1), (6, 1, 0), (9, 0, 2)])

    def test_none_breaks_consecutive(self):
        obs = [(0, 0), (1, 0), (2, 0), (3, 1), (4, 1), (5, None), (6, 1)]
        self.assertEqual(detect_score_changes(obs), [])

    def test_none_preserves_stable_state(self):
        obs = [(0, 0), (1, 0), (2, 0), (3, 1), (4, 1), (5, 1),
               (6, None), (7, 1), (8, 1), (9, 1)]
        self.assertEqual(detect_score_changes(obs), [(3, 0, 1)])

    def test_threshold_one(self):
        self.assertEqual(detect_score_changes([(0, 0), (1, 1), (2, 2)], 1),
                         [(1, 0, 1), (2, 1, 2)])

    def test_threshold_two_and_equal_timestamps(self):
        obs = [(5, 0), (5, 0), (5, 1), (5, 1)]
        self.assertEqual(detect_score_changes(obs, 2), [(5, 0, 1)])

    def test_invalid_and_reversed(self):
        with self.assertRaises(ValueError):
            detect_score_changes([], 0)
        with self.assertRaises(ValueError):
            detect_score_changes([(0, 0), (-1, 0)])
        with self.assertRaises(ValueError):
            detect_score_changes([(0, None), (-1, None)])

    def test_empty_and_nonmutation(self):
        self.assertEqual(detect_score_changes([]), [])
        obs = [(0, 0), (1, 0), (2, 0), (3, None)]
        saved = list(obs)
        detect_score_changes(obs)
        self.assertEqual(obs, saved)


if __name__ == "__main__":
    unittest.main()
