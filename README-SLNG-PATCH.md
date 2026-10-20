# VoiceOps SLNG connectivity patch

This patch changes only these existing project files:
- `app/config.py`
- `app/integrations/slng_client.py`
- `app/main.py`
- `app/static/app.js`

It does not include or replace `.env`, the SQLite database, CSVs, or the rest of your project.

## What changed

- Normalizes `SLNG_API_KEY` so a key stored as either `actual-key` or `Bearer actual-key` does not become `Bearer Bearer actual-key`.
- Tries your configured regional endpoint first, then the global SLNG gateway (`https://api.slng.ai`) for network, routing, and selected gateway/auth failures.
- Keeps SLNG's documented Bearer authentication. It does not send the secret in a URL or switch to undocumented `x-api-key` auth.
- Adds `POST /voice/test`, which makes a real short Aura 2 TTS request. The dashboard's **Check voice status** button now uses this endpoint instead of merely checking whether a key exists.
- Improves failure messages and includes SLNG request IDs when available.
- Cleans up the redundant exception handler in `/voice/speak`.

## Apply it safely

From Terminal, in the original project folder:

```bash
cd "/Users/phanindra/Madmaxx/voiceops 2"
```

Back up the four files before replacing them:

```bash
mkdir -p backup/slng-before-patch
cp app/config.py app/integrations/slng_client.py app/main.py app/static/app.js backup/slng-before-patch/
```

Extract this patch ZIP into the project folder and allow it to replace only the four listed files. Do not replace `.env`.

## Check `.env`

Keep the API key private. These values should be set (use your existing key value locally):

```dotenv
SLNG_BASE_URL=https://eu-west.api.slng.ai
SLNG_FALLBACK_BASE_URL=https://api.slng.ai
SLNG_WORLD_PART=eu
SLNG_STT_MODEL=deepgram/nova:3
SLNG_TTS_MODEL=aura-2-thalia-en
SLNG_TTS_VOICE=aura-2-thalia-en
```

`SLNG_API_KEY` must contain the API key issued by SLNG, not the dashboard URL. It may be the raw key or the key prefixed with `Bearer`; the patched code handles either form. Restart Uvicorn after changing `.env`.

## Run and test

```bash
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`, select **Check voice status**, then click **Read answer aloud** after asking a question.

You can also test the TTS connection from a second Terminal:

```bash
curl -sS -X POST http://127.0.0.1:8000/voice/test
```

A successful result contains `"ok": true`. If both hosts return HTTP 401/403, the key is not accepted by SLNG; no alternative HTTP header can safely bypass that. Verify the key is active and belongs to the correct SLNG workspace, then send SLNG support the request ID shown in the error. Do not share the key.

## Important limits

- This patch can improve routing and key-format handling, but I cannot validate your private key from this environment.
- The endpoint `/voice/test` validates Aura 2 text-to-speech only. To validate STT, record a short clip and choose **Transcribe recording**.
- This project currently uses SLNG's lower-level TTS/STT HTTP APIs; it does not yet create or join a managed SLNG Voice Agent session. That is a separate integration involving SLNG agent/session APIs and their client connection credentials.
- Because `.env` was included in the ZIP uploaded for debugging, rotate/revoke that API key in the SLNG dashboard if it is real, then update the local `.env`. Never include `.env` in future ZIPs.
