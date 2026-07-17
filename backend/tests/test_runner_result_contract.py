from routers.projects_v3 import _parse_structured_runner_result


def test_structured_runner_result_requires_the_completion_contract():
    payload = """{
      "result_summary": "Read-only verification completed",
      "decisions": ["No source files changed"],
      "blockers": [],
      "next_actions": ["Approve the run"],
      "memory_summary": "OpenClaw executor is healthy",
      "verification": ["pytest: 27 passed"]
    }"""
    result = _parse_structured_runner_result(payload)
    assert result is not None
    assert result["result_summary"] == "Read-only verification completed"


def test_structured_runner_result_rejects_future_work_message():
    assert _parse_structured_runner_result("Now let me run all tests") is None


def test_structured_runner_result_accepts_json_code_fence_for_compatibility():
    payload = """```json
    {
      "result_summary": "done",
      "decisions": [],
      "blockers": [],
      "next_actions": [],
      "memory_summary": "done",
      "verification": []
    }
    ```"""
    assert _parse_structured_runner_result(payload)["result_summary"] == "done"
