"""SLNG HTTP integration for Aura 2 TTS and Nova 3 STT.

Authentication follows SLNG's documented scheme: Authorization: Bearer <API key>.
The configured regional host is tried first, followed by the global gateway when
routing/authentication at the first host fails. API keys are never logged or returned.
"""
import json
import time
import asyncio
import os
from pathlib import Path
from typing import Any, Optional, Tuple, List

import httpx

from app.config import (
    SLNG_API_KEY,
    SLNG_BASE_URL,
    SLNG_FALLBACK_BASE_URL,
    SLNG_STT_MODEL,
    SLNG_TTS_MODEL,
    SLNG_TTS_VOICE,
    SLNG_WORLD_PART,
)

# Audio format constants for better error messages
SUPPORTED_AUDIO_FORMATS = {".webm", ".wav", ".mp3", ".m4a", ".mp4", ".ogg", ".flac"}

# VoiceAI API key environment variable names (alternative to SLNG_* for compatibility)
VOICEAI_API_KEY = "VOICEAI_API_KEY"
VOICEAI_API_KEY_PRIORITY = "VOICEAI_API_KEY_PRIORITY"
VOICEAI_BASE_URL = "VOICEAI_BASE_URL"

# Track key cooldowns for rate limiting detection
_KEY_COOLDOWNS: dict[str, float] = {}


def _load_env_file(env_path: Path | None = None) -> None:
    """
    Read key-value pairs from .env file into os.environ without overwriting existing env vars.
    This ensures the API key is never hardcoded.
    """
    if env_path is None:
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if env_path.exists():
        try:
            with env_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip().strip("'\"")
                        if key and key not in os.environ:
                            os.environ[key] = val
        except Exception:
            # If we can't read the env file, continue with existing environment
            pass


def _get_api_keys() -> List[str]:
    """
    Returns prioritized list of SLNG API keys for dynamic failover:
    1. Priority key: from VOICEAI_API_KEY_PRIORITY / SLNG_API_KEY_PRIORITY in .env
    2. Fallback key: from VOICEAI_API_KEY / SLNG_API_KEY in .env
    3. Also check legacy variable names
    """
    _load_env_file()
    keys = []

    # Priority key: check env / .env
    prio = (
        os.environ.get("VOICEAI_API_KEY_PRIORITY")
        or os.environ.get("SLNG_API_KEY_PRIORITY")
        or os.environ.get("VOICE_API_KEY_PRIORITY")
    )
    if prio and prio.strip():
        keys.append(prio.strip())

    # Fallback key: from .env / os.environ
    fallback = (
        os.environ.get("VOICEAI_API_KEY")
        or os.environ.get("SLNG_API_KEY")
        or os.environ.get("VOICE_API_KEY")
        or os.environ.get("SLNG_API_SECRET")  # Legacy support
    )
    if fallback and fallback.strip() and fallback.strip() not in keys:
        keys.append(fallback.strip())

    return keys


def _mark_key_rate_limited(api_key: str, cooldown_seconds: float = 60.0) -> None:
    """
    Temporarily marks an API key as rate-limited / high-usage so subsequent requests
    automatically failover to the alternate key.
    """
    _KEY_COOLDOWNS[api_key] = time.time() + cooldown_seconds


def _is_key_rate_limited(api_key: str) -> bool:
    expiry = _KEY_COOLDOWNS.get(api_key, 0)
    if time.time() < expiry:
        return True
    if api_key in _KEY_COOLDOWNS:
        del _KEY_COOLDOWNS[api_key]
    return False


def _get_active_keys() -> List[str]:
    """
    Returns active keys sorted so available keys come first, preserving priority.
    """
    all_keys = _get_api_keys()
    active = [k for k in all_keys if not _is_key_rate_limited(k)]
    cooling = [k for k in all_keys if _is_key_rate_limited(k)]
    return active if active else cooling


class VoiceUnavailable(RuntimeError):
    """A safe, user-displayable voice configuration or capability error."""


def _normalized_key() -> str:
    _load_env_file()
    key = (SLNG_API_KEY or "").strip().strip('"').strip("'")
    # Also check for VOICEAI_API_KEY as alternative
    if not key:
        key = (os.environ.get("VOICEAI_API_KEY") or "").strip().strip('"').strip("'")
    # Avoid accidentally sending "Bearer Bearer <key>" if .env stores the prefix.
    if key.lower().startswith("bearer "):
        key = key[7:].strip()
    if not key:
        raise VoiceUnavailable(
            "SLNG_API_KEY is missing. Add the API key value (with or without the Bearer prefix) to .env, then restart VoiceOps."
        )
    return key


def _headers(*, json_body: bool = False) -> dict[str, str]:
    # Get active key with failover support
    active_keys = _get_active_keys()
    if not active_keys:
        raise VoiceUnavailable("No valid SLNG API key found. Please check your .env file.")

    # Use the first active key (highest priority available)
    key = active_keys[0]

    # Avoid accidentally sending "Bearer Bearer <key>" if .env stores the prefix.
    if key.lower().startswith("bearer "):
        key = key[7:].strip()

    headers = {"Authorization": f"Bearer {key}"}
    if json_body:
        headers["Content-Type"] = "application/json"
    return headers


def _base_urls() -> list[str]:
    _load_env_file()
    urls = []
    # Check VOICEAI_BASE_URL as alternative to SLNG_BASE_URL
    voiceai_base_url = os.environ.get("VOICEAI_BASE_URL", "").strip().rstrip("/")
    slng_base_url = SLNG_BASE_URL.strip().rstrip("/")
    slng_fallback_base_url = SLNG_FALLBACK_BASE_URL.strip().rstrip("/")

    # Priority order: VOICEAI_BASE_URL, SLNG_BASE_URL, SLNG_FALLBACK_BASE_URL
    for url in (voiceai_base_url, slng_base_url, slng_fallback_base_url):
        if url and url.startswith("https://") and url not in urls:
            urls.append(url)
    if not urls:
        raise VoiceUnavailable("No valid HTTPS SLNG endpoint is configured.")
    return urls


def _request_id(response: httpx.Response) -> str | None:
    for name in ("slng_request_id", "x-request-id", "request-id", "x-slng-request-id"):
        value = response.headers.get(name)
        if value:
            return value[:128]
    try:
        payload = response.json()
        value = payload.get("slng_request_id") or payload.get("request_id")
        return str(value)[:128] if value else None
    except (ValueError, AttributeError):
        return None


def _raise_for_upstream(response: httpx.Response, *, attempted_hosts: list[str] | None = None) -> None:
    if response.is_success:
        return
    request_id = _request_id(response)
    rid = f" SLNG request ID: {request_id}." if request_id else ""
    if response.status_code in (401, 403):
        hosts = ", ".join(attempted_hosts or [])
        host_note = f" Hosts tried: {hosts}." if hosts else ""
        raise VoiceUnavailable(
            f"SLNG rejected the API key (HTTP {response.status_code}). "
            "Confirm the key is active and belongs to the correct SLNG workspace; "
            "the key must be the raw key value, not a dashboard URL. "
            f"{host_note}{rid}"
        )
    raise VoiceUnavailable(
        f"SLNG voice request failed (HTTP {response.status_code}). "
        f"Check the configured model/endpoint. {rid}"
    )


async def _post_with_fallback(
    path: str,
    *,
    headers: dict[str, str],
    timeout: float,
    json_body: dict[str, Any] | None = None,
    files: dict[str, Any] | None = None,
    data: dict[str, str] | None = None,
) -> httpx.Response:
    urls = _base_urls()
    last_error: Exception | None = None
    attempted_hosts: list[str] = []
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        for index, base in enumerate(urls):
            attempted_hosts.append(base)
            try:
                response = await client.post(
                    f"{base}{path}",
                    headers=headers,
                    json=json_body,
                    files=files,
                    data=data,
                )
            except httpx.RequestError as exc:
                last_error = exc
                # Try the second configured host if the regional host has a DNS/TLS/network issue.
                if index + 1 < len(urls):
                    continue
                raise VoiceUnavailable(
                    "Could not reach SLNG over HTTPS from this machine. Check network/DNS and the SLNG endpoint configuration."
                ) from exc

            # 401/403 are retried on the alternate host once: the regional and global
            # gateways may be configured differently for an account. Never change auth scheme.
            if response.status_code in (401, 403, 404, 421, 500, 502, 503, 504) and index + 1 < len(urls):
                continue
            _raise_for_upstream(response, attempted_hosts=attempted_hosts)
            return response

    if last_error:
        raise VoiceUnavailable("Could not reach any configured SLNG endpoint.") from last_error
    raise VoiceUnavailable("SLNG request did not return a response.")


async def speak(text: str) -> tuple[bytes, str]:
    text = (text or "").strip()
    if not text:
        raise VoiceUnavailable("There is no text to read aloud.")
    if len(text) > 10000:
        raise VoiceUnavailable("Text is too long for one Read Aloud request. Select a shorter answer.")
    model = (SLNG_TTS_VOICE or SLNG_TTS_MODEL or "aura-2-thalia-en").strip()
    response = await _post_with_fallback(
        "/v1/tts/deepgram/aura:2",
        headers=_headers(json_body=True),
        timeout=60,
        json_body={
            "model": model,
            "text": text,
        },
    )
    content_type = response.headers.get("content-type", "audio/mpeg")
    if "audio" not in content_type.lower() and "octet-stream" not in content_type.lower():
        raise VoiceUnavailable(
            "SLNG returned a non-audio response. Confirm the Aura 2 voice model and inspect the server logs."
        )
    if not response.content:
        raise VoiceUnavailable("SLNG returned an empty audio response.")
    return response.content, content_type



async def transcribe(
    audio: bytes,
    content_type: str,
    filename: str = "recording.webm",
) -> str:
    """Transcribe uploaded browser audio through SLNG's configured STT endpoint."""
    # Validate input
    if not audio:
        raise VoiceUnavailable("Recording is empty. Please record again.")

    if len(audio) > 20 * 1024 * 1024:  # 20MB limit
        raise VoiceUnavailable("Recording is too large (max 20MB). Please record a shorter clip.")

    # Validate and normalize file extension
    suffix = Path(filename or "recording.webm").suffix.lower()
    if suffix not in SUPPORTED_AUDIO_FORMATS:
        suffix = ".webm"  # Default to webm if unsupported format

    # Basic audio data validation
    if len(audio) < 100:  # Very small audio files are likely invalid
        raise VoiceUnavailable("Recording appears to be too short or empty. Please record again.")

    # Attempt transcription with retry logic and key rotation
    max_retries = 3
    for attempt in range(max_retries + 1):
        try:
            # Get active API key with failover support
            active_keys = _get_active_keys()
            if not active_keys:
                raise VoiceUnavailable("No valid SLNG API key found. Please check your .env file.")

            # Use the first active key (highest priority available)
            key = active_keys[0]

            # Avoid accidentally sending "Bearer Bearer <key>" if .env stores the prefix.
            if key.lower().startswith("bearer "):
                key = key[7:].strip()

            headers = {"Authorization": f"Bearer {key}"}

            # Use the working STT endpoint format from the reference implementation
            # Based on their listen.py: endpoint = f"{base_url}/v1/stt/{model}"
            # With model = "slng/deepgram/nova:3-en"
            response = await _post_with_fallback(
                "/v1/stt/slng/deepgram/nova:3-en",
                headers=headers,
                timeout=30,
                files={
                    "audio": (
                        f"recording{suffix}",
                        audio,
                        content_type or "application/octet-stream",
                    )
                },
                # No extra form data - just send the raw audio file like their implementation
            )

            try:
                payload = response.json()
            except ValueError as exc:
                if attempt < max_retries:
                    # Wait briefly before retrying on JSON parsing errors
                    await asyncio.sleep(0.5 * (attempt + 1))
                    # Rotate to next key on JSON parsing errors
                    if len(active_keys) > 1:
                        _mark_key_rate_limited(key, cooldown_seconds=10.0)
                    continue
                raise VoiceUnavailable(
                    "SLNG returned an invalid transcription response. "
                    "This may indicate temporary service issues. Please try again."
                ) from exc

            # Accept common response structures without assuming one exact schema.
            # Follow the parsing approach from their listen.py
            transcript = ""

            # Check for direct transcript field
            if "transcript" in payload and isinstance(payload["transcript"], str):
                transcript = payload["transcript"].strip()

            # Check for results.channels[0].alternatives[0].transcript format
            if not transcript and isinstance(payload.get("results"), dict):
                channels = payload["results"].get("channels", [])
                if channels and isinstance(channels, list) and len(channels) > 0:
                    first_channel = channels[0]
                    if isinstance(first_channel, dict) and "alternatives" in first_channel:
                        alternatives = first_channel["alternatives"]
                        if alternatives and isinstance(alternatives, list) and len(alternatives) > 0:
                            first_alternative = alternatives[0]
                            if isinstance(first_alternative, dict) and "transcript" in first_alternative:
                                transcript = str(first_alternative["transcript"]).strip()

            # Check for alternative response formats
            if not transcript and isinstance(payload, dict):
                # Try alternative response formats
                if "alternatives" in payload and isinstance(payload["alternatives"], list) and len(payload["alternatives"]) > 0:
                    if isinstance(payload["alternatives"][0], dict) and "transcript" in payload["alternatives"][0]:
                        transcript = payload["alternatives"][0]["transcript"].strip()
                elif "text" in payload and isinstance(payload["text"], str):
                    transcript = payload["text"].strip()

            # Validate that we got a meaningful transcript
            if not isinstance(transcript, str) or not transcript.strip():
                if attempt < max_retries:
                    # Wait briefly before retrying on empty transcript
                    await asyncio.sleep(0.5 * (attempt + 1))
                    # Rotate to next key on empty transcript (possible rate limiting or audio issue)
                    if len(active_keys) > 1:
                        _mark_key_rate_limited(key, cooldown_seconds=10.0)
                    continue
                raise VoiceUnavailable(
                    "SLNG returned no transcript. This could be due to:\n"
                    "1. Audio too quiet or background noise too high\n"
                    "2. Speech not detected in the recording\n"
                    "3. Temporary service issues\n"
                    "Please try recording again in a quieter environment."
                )

            # Success - return the transcript
            return transcript.strip()

        except VoiceUnavailable:
            # Re-raise VoiceUnavailable exceptions immediately (don't retry)
            raise
        except Exception as e:
            if attempt < max_retries:
                # Wait briefly before retrying on unexpected errors
                await asyncio.sleep(1.0 * (attempt + 1))
                # Rotate to next key on unexpected errors
                if len(active_keys) > 1:
                    _mark_key_rate_limited(key, cooldown_seconds=10.0)
                continue
            raise VoiceUnavailable(
                f"Transcription failed after {max_retries + 1} attempts. "
                f"Please check your connection and try again. Error: {str(e)}"
            ) from e

    # This point should not be reached due to the return in the loop
    raise VoiceUnavailable("Transcription failed unexpectedly.")

