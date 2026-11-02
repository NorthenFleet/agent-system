"""Busy describes work, not connectivity; expired heartbeats always win."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from routers.monitoring_router import get_monitoring_agents


@pytest.mark.parametrize("age,expected", [(10, "busy"), (120, "timeout"), (400, "offline")])
def test_busy_cannot_override_expired_heartbeat(age, expected):
    db = MagicMock()
    db.query.return_value.all.return_value = []
    db.query.return_value.join.return_value.order_by.return_value.all.return_value = [
        SimpleNamespace(agent_id="probe", agent_name="probe", status="busy",
                        heartbeat_at=datetime.now(timezone.utc) - timedelta(seconds=age),
                        current_task="test", cpu_usage=1, memory_usage=2,
                        task_queue_len=1, extra_data={})
    ]
    result = get_monitoring_agents(status_filter=None, _user={}, db=db)
    assert result["agents"][0]["status"] == expected
