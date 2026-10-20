import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
# Load project-local .env; an explicitly exported shell variable still takes precedence.
load_dotenv(BASE_DIR / ".env", override=False)

DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
DATABASE_PATH = os.getenv("DATABASE_PATH", str(BASE_DIR / "voiceops.sqlite3"))
# Support either variable name so older .env files don't silently lose the key.
SLNG_API_KEY = (os.getenv("SLNG_API_KEY") or os.getenv("SLNG_API_SECRET") or "").strip()
# This is the endpoint verified by the user's successful standalone TTS test.
SLNG_BASE_URL = os.getenv("SLNG_BASE_URL", "https://in.api.slng.ai").strip().rstrip("/")
# No fallback by default: the global hostname returned NXDOMAIN in the user's DNS tests.
SLNG_FALLBACK_BASE_URL = os.getenv("SLNG_FALLBACK_BASE_URL", "").strip().rstrip("/")
SLNG_REGION = os.getenv("SLNG_REGION", "ap-south-1").strip().lower()
# Retain this compatibility setting for app/main.py; do not send an EU/NA override to India.
SLNG_WORLD_PART = os.getenv("SLNG_WORLD_PART", "").strip().lower()
SLNG_STT_MODEL = os.getenv("SLNG_STT_MODEL", "deepgram/nova:3")
SLNG_TTS_MODEL = os.getenv("SLNG_TTS_MODEL", "aura-2-thalia-en")
SLNG_TTS_VOICE = os.getenv("SLNG_TTS_VOICE", SLNG_TTS_MODEL)
CONFIDENCE_REVIEW_THRESHOLD = float(os.getenv("CONFIDENCE_REVIEW_THRESHOLD", "0.65"))
