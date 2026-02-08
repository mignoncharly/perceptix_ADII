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
bind = "127.0.0.1:8000"

# The maximum number of pending connections
backlog = 2048

# ==============================================================================
# WORKER PROCESSES
# ==============================================================================

# Number of worker processes
# Formula: (2 x CPU cores) + 1
workers = multiprocessing.cpu_count() * 2 + 1

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
accesslog = "/var/log/gemini/access.log"

# Error log - records Gunicorn server errors
errorlog = "/var/log/gemini/error.log"

# The granularity of Error log outputs
# Valid levels: debug, info, warning, error, critical
loglevel = os.getenv("PERCEPTIX_LOG_LEVEL", "info").lower()

# Access log format
access_log_format = (
    '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" '
    '%(D)s %(p)s'
)
# Variables explained:
# %(h)s - remote address
# %(l)s - '-'
# %(u)s - user name
# %(t)s - date of the request
# %(r)s - status line (e.g. GET / HTTP/1.1)
# %(s)s - status
# %(b)s - response length
# %(f)s - referer
# %(a)s - user agent
# %(D)s - request time in microseconds
# %(p)s - process ID

# ==============================================================================
# SERVER MECHANICS
# ==============================================================================

# Daemonize the Gunicorn process (detach & enter background)
daemon = False  # systemd will handle daemonization

# A filename to use for the PID file
pidfile = "/var/run/gemini/gunicorn.pid"

# Switch worker processes to run as this user
user = "perceptix"
group = "perceptix"

# A directory to use for the worker heartbeat temporary file
# If not set, the default temp directory will be used
tmp_upload_dir = None

# Umask to set when daemonizing
umask = 0o022

# ==============================================================================
# SSL (if terminating SSL at Gunicorn instead of Nginx)
# ==============================================================================

# Leave commented if using Nginx for SSL termination
# keyfile = "/etc/letsencrypt/live/yourdomain.com/privkey.pem"
# certfile = "/etc/letsencrypt/live/yourdomain.com/fullchain.pem" 

# ==============================================================================
# SERVER HOOKS
# ==============================================================================

def on_starting(server):
    """
    Called just before the master process is initialized.
    """
    server.log.info("=" * 60)
    server.log.info("Perceptix API Server Starting...")
    server.log.info("=" * 60)
    server.log.info(f"Workers: {workers}")
    server.log.info(f"Worker class: {worker_class}")
    server.log.info(f"Bind: {bind}")
    server.log.info("=" * 60)


def on_reload(server):
    """
    Called to recycle workers during a reload via SIGHUP.
    """
    server.log.info("Perceptix API reloading... recycling workers")


def when_ready(server):
    """
    Called just after the server is started.
    """
    server.log.info("=" * 60)
    server.log.info("Perceptix API is ready to serve requests!")
    server.log.info("=" * 60)


def worker_int(worker):
    """
    Called when a worker receives the SIGINT or SIGQUIT signal.
    """
    worker.log.info(f"Worker {worker.pid} received INT/QUIT signal")


def worker_abort(worker):
    """
    Called when a worker receives the SIGABRT signal.
    """
    worker.log.error(f"Worker {worker.pid} aborted!")


def pre_fork(server, worker):
    """
    Called just before a worker is forked.
    """
    pass


def post_fork(server, worker):
    """
    Called just after a worker has been forked.
    """
    server.log.info(f"Worker spawned (pid: {worker.pid})")


def pre_exec(server):
    """
    Called just before a new master process is forked.
    """
    server.log.info("Forked child, re-executing.")


def worker_exit(server, worker):
    """
    Called just after a worker has been exited.
    """
    server.log.info(f"Worker exited (pid: {worker.pid})")


def on_exit(server):
    """
    Called just before exiting Gunicorn.
    """
    server.log.info("=" * 60)
    server.log.info("Perceptix API shutting down...")
    server.log.info("=" * 60)


# ==============================================================================
# PERFORMANCE
# ==============================================================================

# Load application code before the worker processes are forked
# This can save RAM resources and speed up server boot times
preload_app = True

# ==============================================================================
# REQUEST LIMITS
# ==============================================================================

# The maximum size of HTTP request line in bytes
limit_request_line = 4096

# Limit the number of HTTP headers fields in a request
limit_request_fields = 100

# Limit the allowed size of an HTTP request header field
limit_request_field_size = 8190

# ==============================================================================
# DEBUGGING
# ==============================================================================

# Restart workers when code changes (development only)
reload = os.getenv("GUNICORN_RELOAD", "false").lower() == "true"

# Install a trace function that spews every line executed by the server
spew = False

# Enable check for frontend_available() in workers
check_config = False
