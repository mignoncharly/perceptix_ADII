#!/usr/bin/env python3
"""Quick script to list available Gemini models"""
import os
from google import genai

# Configure API (do not hardcode keys in source)
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise SystemExit("Missing GEMINI_API_KEY in environment.")

client = genai.Client(api_key=api_key)

print("Available Gemini models:")
print("=" * 60)

for model in client.models.list():
    actions = getattr(model, "supported_actions", None) or []
    if "generateContent" in actions:
        print(f"Name: {getattr(model, 'name', '')}")
        display_name = getattr(model, "display_name", None)
        if display_name:
            print(f"Display Name: {display_name}")
        print(f"Supported actions: {actions}")
        print("-" * 60)

client.close()
