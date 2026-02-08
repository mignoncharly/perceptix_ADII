"""
Gunicorn configuration for Perceptix FastAPI application.
This file should be placed at: /home/mignon/gemini/gunicorn_config.py
"""

import multiprocessing
import os

# ==============================================================================
# SERVER SOCKET
# ==============================================================================

# Bind to localhost only (nginx will reverse proxy)
bind = "127.0.0.1:8001"

# The maximum number of pending connections
backlog = 2048

# ==============================================================================
# WORKER PROCESSES
# ==============================================================================

# Number of worker processes
# Formula: (2 x CPU cores) + 1
default_workers = multiprocessing.cpu_count() * 2 + 1
workers = int(os.getenv("WEB_CONCURRENCY", str(default_workers)))


# Worker class - use Uvicorn's worker for ASGI support
worker_class = "uvicorn.workers.UvicornWorker"

# Maximum number of simultaneous clients per worker
worker_connections = 1000

# Workers silent for more than this many seconds are killed and restarted
timeout = 120

# Keep-alive connections on for this many seconds
keepalive = 5

# Maximum number of requests a worker will process before restarting
# Helps prevent memory leaks
max_requests = 1000
max_requests_jitter = 50

# ==============================================================================
# PROCESS NAMING
# ==============================================================================

proc_name = "perceptix-api"

# ==============================================================================
# LOGGING
# ==============================================================================

# Access log - records incoming HTTP requests
accesslog = "/home/mignon/gemini/logs/access.log"

# Error log - records Gunicorn server errors
errorlog = "/home/mignon/gemini/logs/error.log"

# The granularity of Error log outputs
# Valid levels: debug, info, warning, error, critical
loglevel = os.getenv("PERCEPTIX_LOG_LEVEL", "info").lower()

# Access log format
access_log_format = (
    '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" '
    '%(D)s %(p)s'
)

# ==============================================================================
# SERVER MECHANICS
# ==============================================================================

# Daemonize the Gunicorn process (detach & enter background)
daemon = False  # systemd will handle daemonization

# A filename to use for the PID file
# pidfile = "/home/mignon/gemini/run/gunicorn.pid"

# User/Group managed by systemd
# user = "mignon"
# group = "mignon"

# A directory to use for the worker heartbeat temporary file
tmp_upload_dir = None

# Umask to set when daemonizing
umask = 0o022

# ==============================================================================
# SERVER HOOKS
# ==============================================================================

def on_starting(server):
    server.log.info("=" * 60)
    server.log.info("Perceptix API Server Starting...")
    server.log.info("=" * 60)
    server.log.info(f"Workers: {workers}")
    server.log.info(f"Worker class: {worker_class}")
    server.log.info(f"Bind: {bind}")
    server.log.info("=" * 60)

def on_reload(server):
    server.log.info("Perceptix API reloading... recycling workers")

def when_ready(server):
    server.log.info("=" * 60)
    server.log.info("Perceptix API is ready to serve requests!")
    server.log.info("=" * 60)

def worker_int(worker):
    worker.log.info(f"Worker {worker.pid} received INT/QUIT signal")

def worker_abort(worker):
    worker.log.error(f"Worker {worker.pid} aborted!")

def pre_fork(server, worker):
    pass

def post_fork(server, worker):
    server.log.info(f"Worker spawned (pid: {worker.pid})")

def pre_exec(server):
    server.log.info("Forked child, re-executing.")

def worker_exit(server, worker):
    server.log.info(f"Worker exited (pid: {worker.pid})")

def on_exit(server):
    server.log.info("=" * 60)
    server.log.info("Perceptix API shutting down...")
    server.log.info("=" * 60)

# ==============================================================================
# PERFORMANCE
# ==============================================================================

preload_app = False

# ==============================================================================
# REQUEST LIMITS
# ==============================================================================

limit_request_line = 4096
limit_request_fields = 100
limit_request_field_size = 8190

# ==============================================================================
# DEBUGGING
# ==============================================================================

reload = os.getenv("GUNICORN_RELOAD", "false").lower() == "true"
spew = False
check_config = False
