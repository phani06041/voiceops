# VoiceOps — Intelligent Document Exception Copilot

A lightweight FastAPI prototype combining healthcare authorization exceptions with a separate mortgage exception ruleset. Business decisions use deterministic Python rules; a paid LLM is not required.

## What was available and what was built

The provided workspace contained `open_cases.csv`, `approved_cases.csv`, and the master requirements prompt, but no pre-existing application repository or mortgage implementation was mounted. The two CSVs each use the same 14-column healthcare schema. This build preserves both files in `data/`, loads them as read-only inputs, and adds clearly labeled synthetic mortgage cases because no mortgage dataset was provided. It does not claim to have reused teammate code that was not available.

## Features

- Unified canonical case normalization and duplicate/malformed row reporting.
- Separate healthcare and mortgage rule modules behind one exception engine.
- Evidence-grounded case explanations and deterministic query interface.
- Dashboard filters, case detail, stats computed from loaded records, reviewer notes and status changes stored in SQLite.
- Human-review and abstention protections for sensitive cases; recommendation never automatically changes case status.
- Optional SLNG Aura 2 TTS integration; app runs without a key.
- Pytest coverage for core normalization, routing, safety and queries.

## Run locally

Python 3.10+ recommended.

```bash
cd voiceops
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env             # optional; edit values if enabling voice
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000. API docs are at http://127.0.0.1:8000/docs.

## Configuration

`SLNG_API_KEY` is required for real speech synthesis. Never commit `.env`. `SLNG_TTS_VOICE` defaults to `aura-2-thalia-en`. The official SLNG Aura 2 endpoint documented at https://docs.slng.ai/api-reference/endpoints/deepgram-aura-2/aura-2-http is `POST /v1/tts/deepgram/aura:2`, bearer authentication, JSON containing `model` and `text`, and binary audio response. This is implemented.

`SLNG_STT_MODEL=deepgram/nova:3` records the selected STT model. The official SLNG Nova documentation describes streaming WebSocket transcription with raw PCM audio frames. The current dashboard/browser records are not connected to that WebSocket PCM protocol, and `/voice/transcribe` intentionally returns an explicit 503 instead of pretending a WebM file upload is compatible. Complete the streaming audio adapter before claiming real STT works. Typed queries continue to work. See https://docs.slng.ai/llms.txt and the SLNG model catalog at https://slng.ai/voice-ai-catalog for current details.

`CONFIDENCE_REVIEW_THRESHOLD` controls the heuristic review threshold. Scores in this prototype are not calibrated probabilities. `DATA_DIR` and `DATABASE_PATH` can override local paths.

## Data schema

`case_id, domain, exception_text, status, suggested_action, manual_review_required, exception_type, confidence_score, sensitive_case, missing_fields, supporting_evidence, authorization_type`

Streamlined to essential workflow attributes with lifecycle synchronization between `status` (Current Status), `suggested_action` (Suggested Action), and `manual_review_required` (Review Queue Status). Backward-compatibility aliases support `expected_action -> suggested_action`, `expected_type -> exception_type`, `review_queue_status -> manual_review_required`, and `case_status -> status`. `missing_fields` is semicolon-delimited in CSV and represented as an array in the API.

## API

- `GET /health`, `GET /stats`
- `GET /cases` with `domain`, `status`, `exception_type`, `action`, `manual_review`, `authorization_type`, `min_confidence`, `max_confidence`, `limit`, `offset`
- `GET /cases/{case_id}`
- `POST /query` and `POST /cases/{case_id}/query` with `{"question":"..."}`
- `POST /cases/{case_id}/status` with `{"status":"in_review","reason":"Review started"}`
- `POST /cases/{case_id}/notes` with `{"note":"..."}`
- `POST /voice/transcribe` (not yet connected to Nova 3 streaming protocol)
- `POST /voice/speak` with `{"text":"..."}`

## Tests

```bash
pytest -q
```

## Safety and limitations

- Prototype authentication/authorization is not implemented; do not expose it publicly or use real patient/financial data.
- No clinical diagnosis, medical-necessity decision, or automatic authorization approval/denial is performed.
- Sensitive cases always abstain from automated resolution and require review. Fraud is not asserted from anomalies.
- Reviewer state is local SQLite; input CSVs are never mutated.
- The supplied CSVs contain 5 open and 6 resolved healthcare examples, and no mortgage records. The demo adds 3 synthetic mortgage cases. These are observed file counts, not performance metrics.
- No classification performance metric is reported because these small CSVs do not constitute an adequate evaluation protocol and the app uses deterministic rules rather than a trained classifier.


## Voice setup (SLNG)

1. Copy `.env.example` to `.env` and add an active SLNG API key. Never commit `.env`.
2. The default API base URL is `https://eu-west.api.slng.ai`; change it only to a region/endpoint provided for your SLNG account.
3. Install dependencies with `python -m pip install -r requirements.txt`, then restart the server so configuration is reloaded.
4. Use **Start recording → Stop recording → Transcribe recording** to submit browser-recorded audio to the Nova 3 HTTP endpoint. Review the transcript before selecting **Ask**.
5. **Read answer aloud** uses the Aura 2 HTTP endpoint. A `401 Invalid API key` means SLNG rejected the credential; create/verify a key in the SLNG dashboard. Code changes cannot make an invalid key valid.

Nova 3 HTTP endpoint behavior follows the [SLNG Nova 3 documentation](https://docs.slng.ai/api-reference/stt/deepgram-nova-3/nova-3-http); Aura 2 uses the [SLNG Aura 2 documentation](https://docs.slng.ai/api-reference/endpoints/deepgram-aura-2/aura-2-http).
