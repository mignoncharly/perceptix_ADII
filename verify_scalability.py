"""
Verification Script for Phase 3: Scalability
"""
import sys
import os
import requests
import time
import subprocess
from pathlib import Path

# Add project root to path
sys.path.append("/home/mignon/gemini")

API_PORT = 8000
API_URL = f"http://localhost:{API_PORT}/api/v1"

def start_server():
    print("Starting API Server...")
    # Using python -m uvicorn which api.py does internally if run as script, but let's run api.py
    proc = subprocess.Popen(
        [sys.executable, "api.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd="/home/mignon/gemini",
        env={**os.environ, "PERCEPTIX_MODE": "DEMO", "PERCEPTIX_LOG_LEVEL": "INFO"}
    )
    return proc

def wait_for_server():
    print("Waiting for server...", end="")
    for _ in range(30):
        try:
            requests.get(f"http://localhost:{API_PORT}/docs")
            print("Server is up!")
            return True
        except:
            time.sleep(1)
            print(".", end="", flush=True)
    return False

def verify_async_cycle():
    print("\n--- Verifying Async Cycle Execution ---")
    try:
        response = requests.post(f"{API_URL}/cycles/trigger", json={"simulate_failure": False}, timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"Cycle triggered successfully: Cycle ID {data['cycle_id']}")
            return True
        else:
            print(f"Failed to trigger cycle: {response.text}")
            return False
    except Exception as e:
        print(f"Exception during cycle trigger: {e}")
        return False

def verify_dynamic_config():
    print("\n--- Verifying Dynamic Configuration ---")
    
    # 1. Update config
    key = "system.confidence_threshold"
    value = "99.9"
    print(f"Updating {key} to {value}")
    
    try:
        response = requests.post(f"{API_URL}/admin/config", json={"key": key, "value": value}, timeout=5)
        if response.status_code == 200:
            print("Config updated via API.")
            return True
        else:
            print(f"Failed to update config: {response.text}")
            return False
    except Exception as e:
        print(f"Exception during config update: {e}")
        return False

def main():
    proc = start_server()
    try:
        if not wait_for_server():
            print("Server failed to start.")
            # Print stderr to diagnose
            _, stderr = proc.communicate(timeout=1)
            print("STDERR:", stderr.decode())
            sys.exit(1)
            
        if verify_async_cycle():
            print("Async Cycle Check: PASS")
        else:
            print("Async Cycle Check: FAIL")
            
        if verify_dynamic_config():
            print("Dynamic Config Check: PASS")
        else:
            print("Dynamic Config Check: FAIL")
            
    finally:
        print("\nStopping server...")
        proc.terminate()
        try:
            proc.communicate(timeout=5)
        except:
            proc.kill()

if __name__ == "__main__":
    main()
