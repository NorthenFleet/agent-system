import asyncio
import json

import pytest

from agent_messenger import AgentMessenger, OpenClawEmptyResponseError


class _FakeProcess:
    returncode = 0

    def __init__(self, payload):
        self.payload = payload

    async def communicate(self):
        return json.dumps(self.payload, ensure_ascii=False).encode(), b""


def test_extract_openclaw_text_ignores_control_sentinels():
    messenger = AgentMessenger()

    assert messenger._extract_openclaw_text({
        "result": {"payloads": [{"text": "NO_REPLY"}]},
    }) == ""


@pytest.mark.asyncio
async def test_empty_openclaw_response_is_sanitized(monkeypatch):
    payload = {
        "runId": "run-sensitive-id",
        "status": "ok",
        "summary": "completed",
        "result": {
            "payloads": [],
            "meta": {"sessionFile": "/Users/private/session.jsonl", "token": "secret"},
        },
    }

    async def fake_subprocess(*_args, **_kwargs):
        return _FakeProcess(payload)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_subprocess)
    messenger = AgentMessenger()

    with pytest.raises(OpenClawEmptyResponseError) as caught:
        await messenger._call_openclaw("ultra-magnus", "生成图表")

    message = str(caught.value)
    assert message == "智能体本次未生成可审阅内容，请重试。"
    assert "sessionFile" not in message
    assert "run-sensitive-id" not in message
    assert "secret" not in message
