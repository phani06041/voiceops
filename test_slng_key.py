import os
import requests
from dotenv import dotenv_values

# Load configuration
env = dotenv_values(".env")

api_secret = env.get("SLNG_API_KEY")
base_url = "https://in.api.slng.ai"

if not api_secret:
    raise ValueError("SLNG_API_SECRET is missing from .env")

# Test your configured TTS model
url = f"{base_url}/v1/tts/deepgram/aura:2"

headers = {
    "Authorization": f"Bearer {api_secret}",
    "Content-Type": "application/json",
}

payload = {
    "model": "aura-2-thalia-en",
    "text": "Hello! This is a test of the SLNG text to speech API."
}

try:
    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=60
    )

    print("HTTP Status:", response.status_code)

    if response.status_code == 200:
        with open("sling_test.wav", "wb") as audio:
            audio.write(response.content)

        print("SUCCESS! Audio saved as sling_test.wav")
    else:
        print("API Error:", response.text)

except requests.RequestException as e:
    print("Connection Error:", e)