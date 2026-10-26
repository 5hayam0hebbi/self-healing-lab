import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "remediator"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from fastapi.testclient import TestClient  # noqa: E402
from logic import RateLimiter, alerts_to_fix, issue_body  # noqa: E402


def test_only_firing_restart_alerts_are_fixed():
    payload = {
        "alerts": [
            {"status": "firing", "labels": {"alertname": "AppUnhealthy", "remediation": "restart"}},
            {"status": "resolved", "labels": {"alertname": "AppUnhealthy", "remediation": "restart"}},
            {"status": "firing", "labels": {"alertname": "HighErrorRate"}},
        ]
    }
    assert [a["labels"]["alertname"] for a in alerts_to_fix(payload)] == ["AppUnhealthy"]


def test_rate_limiter_blocks_then_recovers():
    now = [0.0]
    limiter = RateLimiter(limit=2, window=60, clock=lambda: now[0])
    assert limiter.allow() and limiter.allow()
    assert not limiter.allow()  # third fix inside the window: a human must look
    now[0] = 61
    assert limiter.allow()


def test_issue_body_has_runbook():
    alert = {"labels": {"alertname": "AppDown"}, "annotations": {"runbook": "memory-leak-hang"}}
    assert "memory-leak-hang" in issue_body(alert)


def test_app_breaks_and_reports_unhealthy():
    import main

    client = TestClient(main.app)
    assert client.get("/health").status_code == 200
    client.post("/chaos/break")
    assert client.get("/health").status_code == 503
    assert client.get("/pay").status_code == 503
    assert b"app_healthy 0.0" in client.get("/metrics/").content
