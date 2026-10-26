"""app/main.py - a tiny 'payments' service that can be told to break, like a real app with a leak."""

import os
import random
import time

from fastapi import FastAPI, Response
from prometheus_client import Counter, Gauge, make_asgi_app

app = FastAPI(title="payments")
app.mount("/metrics", make_asgi_app())  # Prometheus reads numbers from here

REQUESTS = Counter("app_requests_total", "Requests served", ["path", "status"])
HEALTHY = Gauge("app_healthy", "1 when the health check passes, 0 when it fails")
STARTED = Gauge("app_start_time_seconds", "When this process started (resets on every restart)")

state = {"healthy": True}
HEALTHY.set(1)
STARTED.set(time.time())


@app.get("/pay")
def pay():
    if not state["healthy"]:
        REQUESTS.labels("/pay", "503").inc()
        return Response("payments are hanging", status_code=503)
    time.sleep(random.uniform(0.01, 0.05))  # pretend to do work
    REQUESTS.labels("/pay", "200").inc()
    return {"status": "paid"}


@app.get("/health")
def health():
    if state["healthy"]:
        return {"status": "ok"}
    return Response("unhealthy", status_code=503)


@app.post("/chaos/break")
def chaos_break():
    """Simulate a memory-leak hang: the process stays up but stops working."""
    state["healthy"] = False
    HEALTHY.set(0)
    return {"status": "broken"}


@app.post("/chaos/crash")
def chaos_crash():
    """Simulate a crash: the process exits and the container stops."""
    os._exit(1)
