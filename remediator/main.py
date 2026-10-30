"""remediator/main.py - receives alerts, opens a ticket, runs the Ansible runbook, closes the ticket."""

import logging
import os
import subprocess
import time

from fastapi import BackgroundTasks, FastAPI
from github import Tickets
from logic import RateLimiter, alerts_to_fix, issue_body, last_lines, playbook_command
from prometheus_client import Counter, make_asgi_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("remediator")

SERVICE = os.environ.get("TARGET_SERVICE", "app")  # the Docker Compose service to restart
HEALTH_URL = os.environ.get("HEALTH_URL", "http://app:8000/health")
# The runbook as code: restart the service, then wait until its health check passes
PLAYBOOK = os.environ.get("PLAYBOOK", "/app/ansible/restart_service.yml")
DOCKER_SOCKET = os.environ.get("DOCKER_SOCKET", "/var/run/docker.sock")

app = FastAPI(title="remediator")
app.mount("/metrics", make_asgi_app())
FIXES = Counter("remediations_total", "Automatic remediation attempts", ["result"])
limiter = RateLimiter(limit=int(os.environ.get("MAX_FIXES", "3")), window=600)
tickets = Tickets()


def run_playbook() -> tuple[bool, str]:
    """Run the Ansible runbook. Returns (it worked, the end of Ansible's output)."""
    command = playbook_command(PLAYBOOK, SERVICE, HEALTH_URL, DOCKER_SOCKET)
    log.info("running %s", " ".join(command))
    # capture_output keeps Ansible's report, so it can go into the ticket
    result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    output = last_lines(result.stdout + result.stderr)
    log.info("ansible-playbook finished with code %s\n%s", result.returncode, output)
    return result.returncode == 0, output


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
        fixed, report = run_playbook()
    except (OSError, subprocess.TimeoutExpired) as e:  # Ansible missing or stuck
        log.exception("playbook could not run")
        tickets.comment(number, f"The runbook could not run: `{e}`. A human needs to look.")
        FIXES.labels("failed").inc()
        return
    seconds = int(time.time() - started)
    # Ansible's own report goes into the ticket, like a change record
    evidence = f"\n\n```\n{report}\n```"
    if fixed:
        message = f"Ansible restarted `{SERVICE}`; health check passing after {seconds}s. Closing."
        tickets.comment(number, message + evidence)
        tickets.close(number)
        FIXES.labels("fixed").inc()
    else:
        tickets.comment(number, f"The Ansible runbook failed after {seconds}s. Escalating to a human.{evidence}")
        FIXES.labels("failed").inc()


@app.post("/alerts")
def receive(payload: dict, background: BackgroundTasks):
    """Alertmanager posts here; answer fast and do the work in the background."""
    alerts = alerts_to_fix(payload)
    for alert in alerts:
        background.add_task(remediate, alert)
    return {"accepted": len(alerts)}
