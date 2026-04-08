from google import genai
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")

def test_gemma():
    client = genai.Client(api_key=API_KEY)
    print(f"Testing gemma-3-27b-it...")
    try:
        response = client.models.generate_content(
            model="gemma-3-27b-it",
            contents="Say 'ONLINE'"
        )
        print(f"Status: {response.text.strip()}")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_gemma()
