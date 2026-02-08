import os
import shutil
import git
from datetime import datetime, timezone
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SimRepoSetup")

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../data/repos"))

def setup_repo(repo_name, files_content, commit_history):
    repo_path = os.path.join(DATA_DIR, repo_name)
    
    # Clean up existing
    if os.path.exists(repo_path):
        shutil.rmtree(repo_path)
    os.makedirs(repo_path)
    
    # Initialize Repo
    repo = git.Repo.init(repo_path)
    repo.config_writer().set_value("user", "name", "Simulated Dev").release()
    repo.config_writer().set_value("user", "email", "dev@perceptix.ai").release()
    
    # Create valid initial state
    for commit in commit_history:
        # Write files
        for fname, content in commit['files'].items():
            fpath = os.path.join(repo_path, fname)
            os.makedirs(os.path.dirname(fpath), exist_ok=True)
            with open(fpath, 'w') as f:
                f.write(content)
        
        # Add and commit
        repo.index.add(list(commit['files'].keys()))
        repo.index.commit(commit['message'], author=git.Actor(commit['author'], f"{commit['author']}@perceptix.ai"))
        
        logger.info(f"[{repo_name}] Committed: {commit['message']}")

def main():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

    # 1. Inventory Service Repo (Mocking the staleness bug)
    setup_repo("inventory-service", {}, [
        {
            "author": "dev_oops",
            "message": "feat: init inventory sync",
            "files": {
                "src/inventory_sync.py": """
import datetime

def sync_inventory():
    print("Syncing inventory...")
    # Update timestamp
    last_updated = datetime.datetime.now()
    return True
"""
            }
        },
        {
            "author": "dev_oops",
            "message": "chore: temporarily disable sync timestamp for perf testing",
            "files": {
                "src/inventory_sync.py": """
import datetime

def sync_inventory():
    print("Syncing inventory...")
    # Update timestamp
    # last_updated = datetime.datetime.now() # TODO: re-enable after perf test
    return True
"""
            }
        }
    ])

    # 2. Checkout Service Repo (Mocking the schema mismatch)
    setup_repo("checkout-service-api", {}, [
        {
            "author": "j.doe",
            "message": "feat: initial tracker",
            "files": {
                "events/tracker.py": """
def track_order(order_id):
    payload = {
        "id": order_id,
        "tracking_pixel_id": "12345"
    }
    send_event(payload)
"""
            }
        },
        {
            "author": "j.doe",
            "message": "fix: update order attribution logic",
            "files": {
                "events/tracker.py": """
def track_order(order_id):
    payload = {
        "id": order_id,
        "source_id": "12345" # Renamed from tracking_pixel_id
    }
    send_event(payload)
"""
            }
        }
    ])

    print("Simulated repositories setup successfully in data/repos/")

if __name__ == "__main__":
    main()
