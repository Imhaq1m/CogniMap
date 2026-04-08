import os
import requests
import json
from google import genai
from dotenv import load_dotenv
from pathlib import Path

def debug_report():
    load_dotenv(override=True)
    print("\n" + "="*40)
    print("      AI SYSTEM DEBUG REPORT")
    print("="*40)

    # 1. Environment Check
    env_path = Path(".env")
    print(f"\n[1] Environment: {'.env exists' if env_path.exists() else '❌ .env MISSING'}")
    
    gemini_key = os.getenv("GOOGLE_API_KEY")
    if gemini_key:
        print(f"    - Google API Key: Found (starts with {gemini_key[:8]}...)")
    else:
        print("    - ❌ Google API Key: NOT FOUND")

    # 2. Cloud API Connectivity (Gemini/Gemma)
    print("\n[2] Cloud API Status (Google Gemini):")
    if gemini_key:
        try:
            client = genai.Client(api_key=gemini_key)
            # Test specifically for the models we set up
            available_models = [m.name for m in client.models.list()]
            models_to_test = ["models/gemini-3.1-flash-lite-preview", "models/gemma-3-27b-it"]
            for m in models_to_test:
                if m in available_models:
                    print(f"    ✅ {m}: Accessible")
                else:
                    print(f"    ❌ {m}: NOT FOUND/PERMISSION DENIED")
        except Exception as e:
            print(f"    ❌ Cloud API Error: {str(e)[:100]}")
    else:
        print("    - Skipping Cloud tests (No Key)")

    # 3. Local LLM Status (Ollama)
    print("\n[3] Local AI Status (Ollama):")
    ollama_url = "http://localhost:11434/api/tags"
    target_model = "qwen2.5:14b"
    try:
        resp = requests.get(ollama_url, timeout=5)
        if resp.status_code == 200:
            models = [m['name'] for m in resp.json().get('models', [])]
            print(f"    ✅ Ollama Server: ONLINE")
            if target_model in models:
                print(f"    ✅ {target_model}: Loaded and ready")
            else:
                available = ", ".join(models) if models else "None"
                print(f"    ⚠️  {target_model}: NOT FOUND (Available: {available})")
        else:
            print(f"    ❌ Ollama Server: Error {resp.status_code}")
    except requests.exceptions.ConnectionError:
        print("    ❌ Ollama Server: OFFLINE (Is the app running?)")
    except Exception as e:
        print(f"    ❌ Ollama Error: {str(e)}")

    print("\n" + "="*40 + "\n")

if __name__ == "__main__":
    debug_report()
