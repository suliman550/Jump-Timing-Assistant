import unittest

from jump_timing_assistant import TimingController, get_configured_target_ms, get_display_status, get_phase_for_elapsed, get_target_delay_ms


class TimingLogicTests(unittest.TestCase):
    def test_perfect_window_brackets_target(self):
        self.assertEqual(get_phase_for_elapsed(100, 500, 200), "EARLY")
        self.assertEqual(get_phase_for_elapsed(500, 500, 200), "PERFECT")
        self.assertEqual(get_phase_for_elapsed(600, 500, 200), "PERFECT")
        self.assertEqual(get_phase_for_elapsed(720, 500, 200), "LATE")

    def test_target_delay_includes_manual_offset(self):
        self.assertEqual(get_target_delay_ms(450, 60), 510)

    def test_configured_target_defaults_to_4500_ms_and_applies_signed_offset(self):
        self.assertEqual(get_configured_target_ms({}), 4500)
        self.assertEqual(get_configured_target_ms({"timing_offset_ms": -125}), 4375)

    def test_display_status_uses_fixed_jump_window(self):
        self.assertEqual(get_display_status(3499), "WAIT")
        self.assertEqual(get_display_status(3500), "JUMP")
        self.assertEqual(get_display_status(4700), "JUMP")
        self.assertEqual(get_display_status(4701), "TOO LATE")

    def test_display_status_accepts_configured_window(self):
        self.assertEqual(get_display_status(2199, 2200, 3300), "WAIT")
        self.assertEqual(get_display_status(2750, 2200, 3300), "JUMP")
        self.assertEqual(get_display_status(3301, 2200, 3300), "TOO LATE")

    def test_reset_clears_jump_state_and_timer(self):
        controller = TimingController({})
        controller.start_manual()
        controller.jump_pressed = True

        controller.reset_timer()

        self.assertFalse(controller.running)
        self.assertFalse(controller.jump_pressed)
        self.assertEqual(controller.current_status()["status"], "WAIT")
        self.assertEqual(controller.current_status()["timer_ms"], 0.0)


if __name__ == "__main__":
    unittest.main()
