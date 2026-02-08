from config import load_config
import os

def verify_config():
    config = load_config()
    
    print("--- Configuration Verification ---")
    print(f"System Mode: {config.system.mode.value}")
    print(f"Database Type: {config.database.type}")
    print(f"Database Name: {config.database.name}")
    print(f"Gemini API Key: {'Set' if config.api.gemini_api_key else 'Not Set'}")
    print(f"API Port: {config.api.port}")
    print(f"CORS Origins: {config.api.cors_origins}")
    print(f"Slack Webhook: {'Set' if config.notification.slack_webhook_url else 'Not Set'}")
    print(f"Email SMTP: {config.notification.email_smtp_host}:{config.notification.email_smtp_port}")
    
    # Check if a few specific values from .env match
    expected_port = int(os.getenv('API_PORT', 8000))
    if config.api.port == expected_port:
        print("✓ API Port matches .env")
    else:
        print(f"✗ API Port mismatch: {config.api.port} vs {expected_port}")

    expected_db_type = os.getenv('DB_TYPE', 'sqlite')
    if config.database.type == expected_db_type:
        print("✓ Database Type matches .env")
    else:
        print(f"✗ Database Type mismatch: {config.database.type} vs {expected_db_type}")

if __name__ == "__main__":
    verify_config()
