import unittest

from score_detector import detect_score_changes


class ExtendedContract(unittest.TestCase):
    def test_reset_after_confirmed_change(self):
        obs = [(0, 0), (10, 0), (20, 0), (30, 1), (40, 1), (50, 1),
               (60, 2), (70, 2), (80, 2)]
        self.assertEqual(detect_score_changes(obs, reset_timestamps={55}), [(30, 0, 1)])

    def test_reset_during_candidate(self):
        obs = [(0, 0), (1, 0), (2, 0), (3, 1), (4, 1), (5, 1), (6, 1)]
        self.assertEqual(detect_score_changes(obs, reset_timestamps={4}), [])

    def test_reset_equal_timestamp_once(self):
        obs = [(0, 0), (1, 0), (2, 0),
               (3, 1), (3, 1), (3, 1),
               (4, 2), (5, 2), (6, 2)]
        self.assertEqual(detect_score_changes(obs, reset_timestamps={3}),
                         [(4, 1, 2)])

    def test_reset_between_observations(self):
        obs = [(0, 0), (10, 0), (20, 0), (30, 1), (40, 1), (50, 1)]
        self.assertEqual(detect_score_changes(obs, reset_timestamps={25}),
                         [])

    def test_multiple_resets_between(self):
        obs = [(0, 0), (1, 0), (2, 0),
               (10, 1), (11, 1), (12, 1),
               (20, 2), (21, 2), (22, 2)]
        self.assertEqual(detect_score_changes(obs, reset_timestamps={3, 6, 9}),
                         [(20, 1, 2)])

    def test_schedule_start_of_run(self):
        obs = [(0, 0), (10, 0),
               (90, 1), (110, 1),
               (120, 2), (130, 2), (140, 2)]
        self.assertEqual(detect_score_changes(obs, threshold_schedule=[(0, 2), (100, 3)]),
                         [(90, 0, 1), (120, 1, 2)])

    def test_schedule_change_during_run_does_not_rethreshold(self):
        obs = [(0, 0), (1, 0), (2, 0), (90, 1), (105, 1)]
        self.assertEqual(detect_score_changes(obs, threshold_schedule=[(0, 3), (100, 1)]),
                         [])

    def test_schedule_uses_default_before_first(self):
        obs = [(0, 0), (1, 0), (2, 0), (3, 1), (4, 1), (5, 1)]
        self.assertEqual(detect_score_changes(obs, threshold_schedule=[(100, 1)]),
                         [(3, 0, 1)])

    def test_none_restarts_with_new_threshold(self):
        obs = [(0, 0), (1, 0), (2, 0), (90, 1), (95, None),
               (110, 1), (111, 1)]
        self.assertEqual(detect_score_changes(obs, threshold_schedule=[(100, 2)]),
                         [(110, 0, 1)])

    def test_reset_and_schedule_same_time(self):
        obs = [(0, 0), (10, 0), (20, 0),
               (100, 1), (101, 1), (110, 2), (111, 2)]
        self.assertEqual(detect_score_changes(
            obs, reset_timestamps={100}, threshold_schedule=[(100, 2)]
        ), [(110, 1, 2)])

    def test_invalid_schedule_and_keyword_only(self):
        for schedule in [[(0, 0)], [(10, 2), (5, 2)], [(1, 2), (1, 3)], [(0, True)]]:
            with self.subTest(schedule=schedule):
                with self.assertRaises(ValueError):
                    detect_score_changes([], threshold_schedule=schedule)
        with self.assertRaises(TypeError):
            detect_score_changes([], 3, set())

    def test_inputs_not_modified(self):
        obs = [(0, 0), (1, 0), (2, 0), (3, 1), (4, 1), (5, 1)]
        resets = {3}
        schedule = [(0, 2), (4, 3)]
        saved_obs, saved_resets, saved_schedule = list(obs), set(resets), list(schedule)
        detect_score_changes(obs, reset_timestamps=resets, threshold_schedule=schedule)
        self.assertEqual((obs, resets, schedule),
                         (saved_obs, saved_resets, saved_schedule))

    def test_empty_after_reset(self):
        self.assertEqual(detect_score_changes([], reset_timestamps={1, 3}), [])


if __name__ == "__main__":
    unittest.main()
