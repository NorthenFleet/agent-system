import asyncio

import services.finance_review_orchestrator as module


class _Coordinator:
    def __init__(self):
        self.review = None
        self.failure = None

    def get_agent_job(self, job_id, *, agent_id):
        assert agent_id == "inspector"
        return {
            "id": job_id,
            "status": "needs_review",
            "operation_type": "reimbursement",
            "request_text": "报销100元车票",
            "normalized_payload": {"total_amount": "100.00"},
            "validation_report": {"valid": True, "errors": []},
            "lock_version": 2,
        }

    def submit_review(self, job_id, **payload):
        self.review = {"job_id": job_id, **payload}
        return {"job": {"id": job_id, "status": "validated"}, "review": payload}

    def record_review_failure(self, job_id, *, error):
        self.failure = {"job_id": job_id, "error": error}


class _Messenger:
    def __init__(self, response):
        self.response = response

    async def request_agent(self, agent_id, prompt, *, timeout_seconds):
        assert agent_id == "inspector"
        assert "不要调用任何工具" in prompt
        assert timeout_seconds == 180
        return self.response


class _TimeoutMessenger:
    async def request_agent(self, agent_id, prompt, *, timeout_seconds):
        assert agent_id == "inspector"
        assert timeout_seconds == 180
        raise asyncio.TimeoutError("OpenClaw review timeout")


def test_orchestrator_submits_structured_independent_review(monkeypatch):
    coordinator = _Coordinator()
    monkeypatch.setattr(module, "finance_intake_coordinator", coordinator)
    monkeypatch.setattr(
        module,
        "agent_messenger",
        _Messenger(
            '{"decision":"approve","summary":"金额一致","findings":[],"confidence":0.94}'
        ),
    )

    result = asyncio.run(module.FinanceReviewOrchestrator().review_job("job-1"))

    assert result["status"] == "completed"
    assert coordinator.review["reviewer_agent_id"] == "inspector"
    assert coordinator.review["expected_version"] == 2
    assert coordinator.failure is None


def test_orchestrator_records_malformed_ai_response(monkeypatch):
    coordinator = _Coordinator()
    monkeypatch.setattr(module, "finance_intake_coordinator", coordinator)
    monkeypatch.setattr(module, "agent_messenger", _Messenger("not json"))

    result = asyncio.run(module.FinanceReviewOrchestrator().review_job("job-2"))

    assert result["status"] == "failed"
    assert coordinator.failure["job_id"] == "job-2"


def test_orchestrator_records_openclaw_timeout(monkeypatch):
    coordinator = _Coordinator()
    monkeypatch.setattr(module, "finance_intake_coordinator", coordinator)
    monkeypatch.setattr(module, "agent_messenger", _TimeoutMessenger())

    result = asyncio.run(module.FinanceReviewOrchestrator().review_job("job-timeout"))

    assert result["status"] == "failed"
    assert result["job_id"] == "job-timeout"
    assert "timeout" in result["error"].lower()
    assert coordinator.review is None
    assert coordinator.failure == {
        "job_id": "job-timeout",
        "error": "OpenClaw review timeout",
    }
