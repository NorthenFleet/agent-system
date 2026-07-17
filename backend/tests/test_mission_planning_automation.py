import unittest

from services.mission_planning_automation import evaluate_signals


class MissionPlanningAutomationTests(unittest.TestCase):
    def test_normal_progress_has_no_suggestion(self):
        suggestions, state = evaluate_signals(
            {"running": True, "tick_count": 12, "total_replans": 0, "last_eval_status": "NORMAL", "plan_summary": {"done": 1}},
            {"run_id": "run-1", "last_tick_count": 10, "last_done": 1, "last_total_replans": 0},
            run_id="run-1",
            now_epoch=1000,
        )
        self.assertEqual(suggestions, [])
        self.assertEqual(state["stagnant_checks"], 0)

    def test_three_stagnant_samples_propose_replan(self):
        state = {"run_id": "run-1", "last_tick_count": 10, "last_done": 1}
        suggestions = []
        for second in (1000, 1015, 1030):
            suggestions, state = evaluate_signals(
                {"running": True, "tick_count": 10, "total_replans": 0, "last_eval_status": "NORMAL", "plan_summary": {"done": 1}},
                state,
                run_id="run-1",
                now_epoch=second,
            )
        self.assertEqual(suggestions[0]["rule_id"], "execution_stagnation")
        self.assertEqual(suggestions[0]["tool_name"], "replan")

    def test_persistent_urgent_proposes_replan(self):
        suggestions, _ = evaluate_signals(
            {
                "running": True,
                "tick_count": 20,
                "total_replans": 1,
                "consecutive_urgent": 3,
                "last_eval_status": "URGENT",
                "eval_score": 0.82,
                "last_tick": {"replan_triggered": False},
                "plan_summary": {"done": 2},
            },
            {"run_id": "run-1", "last_tick_count": 19, "last_done": 2, "last_total_replans": 1},
            run_id="run-1",
            now_epoch=1000,
        )
        self.assertEqual(suggestions[0]["rule_id"], "persistent_urgent")

    def test_error_event_proposes_stop_and_is_deduplicated(self):
        snapshot = {
            "running": True,
            "tick_count": 5,
            "recent_events": [{"timestamp": 9, "event_type": "tick_exception", "level": "error", "message": "engine failed"}],
            "plan_summary": {"done": 0},
        }
        first, state = evaluate_signals(snapshot, {}, run_id="run-1", now_epoch=1000)
        second, _ = evaluate_signals(snapshot, state, run_id="run-1", now_epoch=1015)
        self.assertEqual(first[0]["tool_name"], "stop_run")
        self.assertEqual(second, [])

    def test_replan_storm_proposes_stop(self):
        suggestions, _ = evaluate_signals(
            {"running": True, "tick_count": 20, "total_replans": 8, "plan_summary": {"done": 1}},
            {"run_id": "run-1", "last_tick_count": 19, "last_done": 1, "last_total_replans": 4},
            run_id="run-1",
            now_epoch=1000,
        )
        self.assertEqual(suggestions[0]["rule_id"], "replan_storm")
        self.assertEqual(suggestions[0]["severity"], "critical")

    def test_first_sample_uses_existing_counts_as_baseline(self):
        suggestions, state = evaluate_signals(
            {"running": True, "tick_count": 40, "total_replans": 12, "plan_summary": {"done": 2}},
            {},
            run_id="run-new",
            now_epoch=1000,
        )
        self.assertEqual(suggestions, [])
        self.assertEqual(state["last_total_replans"], 12)

    def test_error_before_run_start_is_ignored(self):
        suggestions, _ = evaluate_signals(
            {
                "running": True,
                "tick_count": 1,
                "recent_events": [{"timestamp": 90, "event_type": "tick_exception", "level": "error", "message": "old"}],
                "plan_summary": {"done": 0},
            },
            {},
            run_id="run-new",
            run_started_epoch=100,
            now_epoch=110,
        )
        self.assertEqual(suggestions, [])


if __name__ == "__main__":
    unittest.main()
