"""remediator/logic.py - the decisions, kept separate from Docker and GitHub so they are easy to test."""

import time
from collections import deque


def alerts_to_fix(payload: dict) -> list[dict]:
    """Firing alerts from an Alertmanager webhook that are labelled remediation=restart."""
    return [
        a
        for a in payload.get("alerts", [])
        if a.get("status") == "firing" and a.get("labels", {}).get("remediation") == "restart"
    ]


class RateLimiter:
    """Allow at most `limit` automatic fixes per `window` seconds; after that a human must look."""

    def __init__(self, limit: int = 3, window: float = 600, clock=time.monotonic):
        self.limit, self.window, self.clock = limit, window, clock
        self.history: deque[float] = deque()

    def allow(self) -> bool:
        now = self.clock()
        while self.history and now - self.history[0] > self.window:
            self.history.popleft()
        if len(self.history) >= self.limit:
            return False
        self.history.append(now)
        return True


def issue_body(alert: dict) -> str:
    labels, notes = alert.get("labels", {}), alert.get("annotations", {})
    return (
        f"**Alert:** {labels.get('alertname', 'unknown')} ({labels.get('severity', 'n/a')})\n\n"
        f"**Summary:** {notes.get('summary', '')}\n\n"
        f"**Started:** {alert.get('startsAt', '')}\n\n"
        f"**Runbook:** {notes.get('runbook', 'none')}\n\n"
        "The remediator is restarting the service and will report back here."
    )
