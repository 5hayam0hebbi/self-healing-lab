"""remediator/main.py - receives alerts, opens a ticket, restarts the service, checks it, closes the ticket."""

import logging
import os
import time

import docker
import requests
from fastapi import BackgroundTasks, FastAPI
from github import Tickets
from logic import RateLimiter, alerts_to_fix, issue_body
from prometheus_client import Counter, make_asgi_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("remediator")

SERVICE = os.environ.get("TARGET_SERVICE", "app")  # the Docker Compose service to restart
HEALTH_URL = os.environ.get("HEALTH_URL", "http://app:8000/health")

app = FastAPI(title="remediator")
app.mount("/metrics", make_asgi_app())
FIXES = Counter("remediations_total", "Automatic remediation attempts", ["result"])
limiter = RateLimiter(limit=int(os.environ.get("MAX_FIXES", "3")), window=600)
tickets = Tickets()


def healthy(wait: int = 60) -> bool:
    """Poll the health check for up to `wait` seconds."""
    deadline = time.time() + wait
    while time.time() < deadline:
        try:
            if requests.get(HEALTH_URL, timeout=2).status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(2)
    return False


def restart_service() -> None:
    client = docker.from_env()  # talks to Docker through the mounted socket
    containers = client.containers.list(all=True, filters={"label": f"com.docker.compose.service={SERVICE}"})
    if not containers:
        raise RuntimeError(f"no container found for service '{SERVICE}'")
    for c in containers:
        log.info("restarting %s", c.name)
        c.restart(timeout=5)


def remediate(alert: dict) -> None:
    name = alert["labels"].get("alertname", "alert")
    if not limiter.allow():
        number = tickets.open(f"[needs human] {name}: too many automatic restarts", issue_body(alert), ["needs-human"])
        log.warning("rate limit hit, escalated to issue #%s", number)
        FIXES.labels("escalated").inc()
        return
    number = tickets.open(f"[auto-heal] {name}", issue_body(alert), ["auto-heal"])
    started = time.time()
    try:
        restart_service()
        fixed = healthy()
    except Exception as e:  # Docker unreachable, container missing
        log.exception("restart failed")
        tickets.comment(number, f"Restart failed: `{e}`. A human needs to look.")
        FIXES.labels("failed").inc()
        return
    seconds = int(time.time() - started)
    if fixed:
        tickets.comment(number, f"Restarted `{SERVICE}`; health check passing after {seconds}s. Closing.")
        tickets.close(number)
        FIXES.labels("fixed").inc()
    else:
        tickets.comment(number, f"Restarted `{SERVICE}` but health is still failing after {seconds}s. Escalating.")
        FIXES.labels("failed").inc()


@app.post("/alerts")
def receive(payload: dict, background: BackgroundTasks):
    """Alertmanager posts here; answer fast and do the work in the background."""
    alerts = alerts_to_fix(payload)
    for alert in alerts:
        background.add_task(remediate, alert)
    return {"accepted": len(alerts)}
