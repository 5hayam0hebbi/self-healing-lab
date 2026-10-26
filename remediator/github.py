"""remediator/github.py - open, comment on and close GitHub Issues (our stand-in for ServiceNow)."""

import logging
import os

import requests

log = logging.getLogger("remediator")
API = "https://api.github.com"


class Tickets:
    def __init__(self):
        self.token = os.environ.get("GITHUB_TOKEN", "")
        self.repo = os.environ.get("GITHUB_REPO", "")
        self.enabled = bool(self.token and self.repo)
        if not self.enabled:
            log.warning("GITHUB_TOKEN or GITHUB_REPO not set: tickets will only be logged")

    def _call(self, method: str, path: str, **body):
        if not self.enabled:
            log.info("ticket %s %s %s", method, path, body)
            return {"number": 0}
        r = requests.request(
            method,
            f"{API}/repos/{self.repo}{path}",
            json=body,
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json"},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()

    def open(self, title: str, body: str, labels: list[str]) -> int:
        return self._call("POST", "/issues", title=title, body=body, labels=labels)["number"]

    def comment(self, number: int, body: str) -> None:
        self._call("POST", f"/issues/{number}/comments", body=body)

    def close(self, number: int) -> None:
        self._call("PATCH", f"/issues/{number}", state="closed")
