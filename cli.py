#!/usr/bin/env python3
"""
Perceptix CLI
Command line interface for interacting with the Perceptix system.
"""
import os
import sys
import argparse
import logging
import time
import asyncio

from rich.console import Console
from rich.panel import Panel
from rich.logging import RichHandler  # Rich logging handler [web:144]

from main import PerceptixSystem


console = Console()



def load_env_file():
    """Manually load .env file since python-dotenv is not installed."""
    env_path = os.path.join(os.getcwd(), '.env')
    if os.path.exists(env_path):
        try:
            with open(env_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        # Remove quotes if present
                        if (value.startswith('"') and value.endswith('"')) or \
                           (value.startswith("'") and value.endswith("'")):
                            value = value[1:-1]
                        
                        if key not in os.environ:
                            os.environ[key] = value
        except Exception as e:
            # Just ignore if we can't read it, logging isn't set up yet
            pass


class DropJsonInfoFilter(logging.Filter):
    """
    Demo output helper:
    Drop INFO log lines that are just JSON blobs like: {"timestamp": "...", ...}
    """
    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno == logging.INFO:
            msg = record.getMessage().lstrip()
            if msg.startswith("{") and msg.endswith("}"):
                return False
        return True


def setup_cli_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()

    handler = RichHandler(
        rich_tracebacks=True,
        show_path=False,
        show_time=True,
        show_level=True,
    )
    handler.setLevel(level)
    handler.addFilter(DropJsonInfoFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    root.addHandler(handler)

    # Optional: reduce noise in demos
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def run_single_cycle(simulate_failure: bool = False):
    """Run a single analysis cycle."""
    console.print(Panel.fit("Initializing Perceptix System...", border_style="cyan"))

    try:
        with PerceptixSystem() as system:
            console.print(
                Panel.fit(
                    f"Mode: {system.config.system.mode.value}\n"
                    f"Data Source: {system.config.observer.data_source_type} ({system.config.observer.data_source_path})",
                    title="Perceptix",
                    border_style="cyan",
                )
            )

            console.print(
                Panel.fit(
                    f"Running cycle 1\nSimulate Failure: {simulate_failure}",
                    border_style="blue",
                )
            )

            start = time.time()
            report = asyncio.run(system.run_cycle(1, simulate_failure=simulate_failure))
            duration = time.time() - start

            if report:
                console.print(
                    Panel.fit(
                        f"Time: {duration:.2f}s\n"
                        f"Status: Anomaly detected\n"
                        f"Type: {report.incident_type.value}\n"
                        f"Confidence: {report.final_confidence_score}%\n"
                        f"Summary: {report.root_cause_analysis}\n"
                        f"Report ID: {report.report_id}",
                        title="Incident",
                        border_style="red",
                    )
                )
            else:
                console.print(
                    Panel.fit(
                        f"Time: {duration:.2f}s\nStatus: System healthy (no anomalies).",
                        title="Result",
                        border_style="green",
                    )
                )

    except Exception as e:
        logging.getLogger("PerceptixCLI").exception("CLI error")
        console.print(Panel.fit(f"Error: {e}", border_style="red"))
        sys.exit(1)


def main():
    load_env_file()
    setup_cli_logging()

    parser = argparse.ArgumentParser(description="Perceptix CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    run_parser = subparsers.add_parser("run", help="Run a system cycle")
    run_parser.add_argument("--simulate-failure", action="store_true", help="Simulate a failure condition")

    args = parser.parse_args()

    if args.command == "run":
        run_single_cycle(args.simulate_failure)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
