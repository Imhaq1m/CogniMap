from google import genai
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")

def list_available_models():
    client = genai.Client(api_key=API_KEY)
    print(f"Checking models for key: {API_KEY[:10]}...")
    try:
        for model in client.models.list():
            print(f" - {model.name}")
    except Exception as e:
        print(f"❌ Error listing models: {e}")

if __name__ == "__main__":
    list_available_models()
