import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.integrations.slng_client import transcribe, VoiceUnavailable


@pytest.mark.asyncio
async def test_transcribe_success():
    """Test successful transcription"""
    # Mock the HTTP response - create a regular Mock for the response object
    # since httpx.Response is not async, but _post_with_fallback is async
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "transcript": "This is a test transcription"
    }
    mock_response.is_success = True

    # Mock the _post_with_fallback function to return our mock response when awaited
    with patch('app.integrations.slng_client._post_with_fallback', return_value=mock_response) as mock_post:
        # Mock _get_active_keys to return a test key
        with patch('app.integrations.slng_client._get_active_keys', return_value=['test-key']):
            # Use audio data that's long enough to pass validation (>= 100 bytes)
            audio_data = b"x" * 150  # 150 bytes of fake audio data
            result = await transcribe(audio_data, "audio/webm", "test.webm")
            assert result == "This is a test transcription"
            # Verify the mock was called
            mock_post.assert_called()


@pytest.mark.asyncio
async def test_transcribe_empty_audio():
    """Test transcription with empty audio data"""
    with pytest.raises(VoiceUnavailable, match="Recording is empty"):
        await transcribe(b"", "audio/webm", "test.webm")


@pytest.mark.asyncio
async def test_transcribe_large_audio():
    """Test transcription with audio that's too large"""
    large_audio = b"x" * (21 * 1024 * 1024)  # 21MB > 20MB limit
    with pytest.raises(VoiceUnavailable, match="Recording is too large"):
        await transcribe(large_audio, "audio/webm", "test.webm")


@pytest.mark.asyncio
async def test_transcribe_no_api_key():
    """Test transcription when no API key is available"""
    with patch('app.integrations.slng_client._get_active_keys', return_value=[]):
        with pytest.raises(VoiceUnavailable, match="No valid SLNG API key found"):
            # Use audio data that's long enough to pass validation (>= 100 bytes)
            audio_data = b"x" * 150  # 150 bytes of fake audio data
            await transcribe(audio_data, "audio/webm", "test.webm")


@pytest.mark.asyncio
async def test_transcribe_retry_on_json_error():
    """Test that transcription retries on JSON parsing errors"""
    # Mock responses for retry scenario
    mock_response_invalid = MagicMock()
    mock_response_invalid.json.side_effect = ValueError("Invalid JSON")
    mock_response_invalid.is_success = True

    mock_response_valid = MagicMock()
    mock_response_valid.json.return_value = {"transcript": "Success on retry"}
    mock_response_valid.is_success = True

    call_count = 0
    def mock_post_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return mock_response_invalid
        return mock_response_valid

    with patch('app.integrations.slng_client._post_with_fallback', side_effect=mock_post_side_effect):
        with patch('app.integrations.slng_client._get_active_keys', return_value=['test-key']):
            with patch('app.integrations.slng_client._is_key_rate_limited', return_value=False):
                # Use audio data that's long enough to pass validation (>= 100 bytes)
                audio_data = b"x" * 150  # 150 bytes of fake audio data
                result = await transcribe(audio_data, "audio/webm", "test.webm")
                assert result == "Success on retry"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])