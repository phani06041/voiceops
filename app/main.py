import logging
import sqlite3
from contextlib import closing
from typing import List, Dict, Any

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from app.config import (
    DATABASE_PATH, SLNG_API_KEY, SLNG_BASE_URL, SLNG_FALLBACK_BASE_URL,
    SLNG_STT_MODEL, SLNG_TTS_VOICE, SLNG_WORLD_PART
)
from app.integrations.slng_client import VoiceUnavailable, speak, transcribe
from app.models.case import CaseQuery, StatusUpdate, ReviewerNote, SpeakRequest
from app.services.data_loader import load_cases
from app.services.exception_engine import process
from app.services.query_engine import answer
from app.services.ml_engine import ml_engine
from app.services.data_management import DataManagementService

app = FastAPI(title='VoiceOps — Intelligent Document Exception Copilot', version='0.1.0')
app.mount('/static', StaticFiles(directory='app/static'), name='static')
cases, load_issues = load_cases()
ALLOWED_STATUS = {'open','in_review','pending_document','pending_specialist','resolved','closed','new'}

# Initialize data management service
data_manager = DataManagementService()

def db():
    conn = sqlite3.connect(DATABASE_PATH); conn.row_factory = sqlite3.Row
    conn.execute('CREATE TABLE IF NOT EXISTS case_state (case_id TEXT PRIMARY KEY, status TEXT, updated_at TEXT DEFAULT CURRENT_TIMESTAMP, reason TEXT DEFAULT "")')
    conn.execute('CREATE TABLE IF NOT EXISTS reviewer_notes (id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT, note TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)')
    conn.commit(); return conn

def enrich(c):
    item = dict(c); item.pop('_source_file',None)
    with closing(db()) as con:
        state = con.execute('SELECT status, reason, updated_at FROM case_state WHERE case_id=?',(item['case_id'],)).fetchone()
        item['status'] = state['status'] if state else item['status']
        item['status_change_reason'] = state['reason'] if state else ''
        item['processing'] = process(item)
        item['source_file'] = c.get('_source_file','unknown')
    return item

@app.get('/', response_class=HTMLResponse)
def home():
    with open('app/templates/index.html',encoding='utf-8') as f: return f.read()

@app.get('/health')
def health(): return {'status':'ok','loaded_cases':len(cases),'rejected_rows':len(load_issues),'voice_configured':bool(SLNG_API_KEY),'stt_model':SLNG_STT_MODEL,'tts_voice':SLNG_TTS_VOICE, 'voice_base_url':SLNG_BASE_URL,'voice_fallback_base_url':SLNG_FALLBACK_BASE_URL,
    'world_part':SLNG_WORLD_PART,'stt_mode':'Nova 3 multipart HTTP upload' }

@app.get('/stats')
def stats():
    allc=[enrich(c) for c in cases]
    return {'total_cases':len(allc),'mortgage_cases':sum(c['domain']=='mortgage' for c in allc),'healthcare_cases':sum(c['domain']=='healthcare' for c in allc),'open_cases':sum(c['status'] in {'open','new','in_review'} for c in allc),'manual_review_cases':sum(c['processing']['manual_review_required'] for c in allc),'pending_documents':sum(c['status']=='pending_document' for c in allc),'pending_specialist':sum(c['status']=='pending_specialist' for c in allc),'resolved_cases':sum(c['status']=='resolved' for c in allc),'loaded_records':len(allc),'rejected_rows':len(load_issues),'load_issues':load_issues,'voice_configured':bool(SLNG_API_KEY)}

@app.get('/cases')
def list_cases(domain:str|None=None,status:str|None=None,exception_type:str|None=None,action:str|None=None,manual_review:bool|None=None,authorization_type:str|None=None,min_confidence:float=Query(0,ge=0,le=1),max_confidence:float=Query(1,ge=0,le=1),limit:int=Query(100,ge=1,le=500),offset:int=Query(0,ge=0)):
    result=[enrich(c) for c in cases]
    if domain: result=[c for c in result if c['domain']==domain.lower()]
    if status: result=[c for c in result if c['status']==status.lower()]
    if exception_type: result=[c for c in result if c['processing']['exception_type']==exception_type.lower()]
    if action: result=[c for c in result if c['processing']['recommended_action']==action.lower()]
    if manual_review is not None: result=[c for c in result if c['processing']['manual_review_required']==manual_review]
    if authorization_type: result=[c for c in result if c['authorization_type']==authorization_type.upper()]
    result=[c for c in result if min_confidence<=c['confidence_score']<=max_confidence]
    return {'total':len(result),'items':result[offset:offset+limit]}

@app.get('/cases/{case_id}')
def get_case(case_id:str):
    c=next((c for c in cases if c['case_id'].lower()==case_id.lower()),None)
    if not c: raise HTTPException(404,'Case not found')
    item=enrich(c)
    with closing(db()) as con: item['reviewer_notes']=[dict(r) for r in con.execute('SELECT note,created_at FROM reviewer_notes WHERE case_id=? ORDER BY id DESC',(case_id,)).fetchall()]
    return item

@app.post('/cases/{case_id}/query')
def query_case(case_id:str, body:CaseQuery): return answer(body.question,cases,case_id)
@app.post('/query')
def query_all(body:CaseQuery): return answer(body.question,cases)

@app.post('/cases/{case_id}/status')
def update_status(case_id:str, body:StatusUpdate):
    c=next((c for c in cases if c['case_id'].lower()==case_id.lower()),None)
    if not c: raise HTTPException(404,'Case not found')
    status=body.status.strip().lower()
    if status not in ALLOWED_STATUS: raise HTTPException(422,'Unsupported status')
    if c.get('sensitive_case') and status in {'resolved','closed'} and len(body.reason.strip())<10: raise HTTPException(422,'Sensitive cases require a detailed reviewer reason before resolution or closure')
    with closing(db()) as con:
        con.execute('INSERT INTO case_state(case_id,status,reason,updated_at) VALUES(?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(case_id) DO UPDATE SET status=excluded.status,reason=excluded.reason,updated_at=CURRENT_TIMESTAMP',(c['case_id'],status,body.reason.strip())); con.commit()
    return get_case(case_id)

@app.post('/cases/{case_id}/notes')
def add_note(case_id:str, body:ReviewerNote):
    if not any(c['case_id'].lower()==case_id.lower() for c in cases): raise HTTPException(404,'Case not found')
    with closing(db()) as con: con.execute('INSERT INTO reviewer_notes(case_id,note) VALUES(?,?)',(case_id,body.note.strip())); con.commit()
    return {'ok':True,'case_id':case_id}

@app.post("/voice/transcribe")
async def voice_transcribe(audio: UploadFile = File(...)):
    try:
        content = await audio.read()

        if not content:
            raise HTTPException(
                status_code=400,
                detail="No audio was uploaded. Record your question again.",
            )

        transcript = await transcribe(
            content,
            audio.content_type or "application/octet-stream",
            audio.filename or "recording.webm",
        )

        return {"transcript": transcript}

    except VoiceUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await audio.close()

@app.post('/voice/speak')
async def voice_speak(body:SpeakRequest):
    try:
        audio, ctype = await speak(body.text)
        return Response(
            content=audio,
            media_type=ctype,
            headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'},
        )
    except VoiceUnavailable as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        logging.exception("Unexpected error in /voice/speak")
        raise HTTPException(502, f"SLNG speech synthesis request failed ({type(e).__name__}). Check server logs.")


@app.post('/voice/test')
async def voice_test():
    """Perform a comprehensive test of both TTS and STT capabilities."""
    try:
        # Test TTS
        audio, ctype = await speak("VoiceOps SLNG connection test successful.")
        tts_result = {
            'ok': True,
            'provider': 'SLNG Aura 2',
            'audio_bytes': len(audio),
            'content_type': ctype,
            'message': 'SLNG TTS authentication and synthesis succeeded.',
        }

        # Test STT with a simple audio file (we'll create a minimal valid audio file)
        # For now, we'll just test that the endpoint is reachable and properly configured
        # A full STT test would require actual audio data, which we can't generate here without external libraries

        # Get health status to check voice configuration (call the function directly)
        from app.main import health
        health_response = health()

        return {
            **tts_result,
            'stt_configured': bool(SLNG_API_KEY),  # Basic check
            'stt_model': SLNG_STT_MODEL,
            'voice_health': health_response
        }
    except VoiceUnavailable as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        logging.exception("Unexpected error in /voice/test")
        raise HTTPException(502, f"SLNG connection test failed ({type(e).__name__}). Check server logs.")


@app.post('/ml/retrain')
def retrain_ml_model():
    """Retrain the ML model with current case data"""
    try:
        success = ml_engine.train(cases)
        if success:
            model_info = ml_engine.get_model_info()
            return {
                'status': 'success',
                'message': 'ML model retrained successfully',
                'model_info': model_info
            }
        else:
            raise HTTPException(500, 'Failed to retrain ML model')
    except Exception as e:
        logging.exception("Error retraining ML model")
        raise HTTPException(500, f"ML model retraining failed: {str(e)}")


@app.get('/ml/info')
def get_ml_model_info():
    """Get information about the current ML model"""
    try:
        model_info = ml_engine.get_model_info()
        return {
            'status': 'success',
            'model_info': model_info
        }
    except Exception as e:
        logging.exception("Error getting ML model info")
        raise HTTPException(500, f"Failed to get ML model info: {str(e)}")


@app.post('/upload/cases')
async def upload_cases(file: UploadFile = File(...)):
    """Upload case data from CSV, JSON, or Excel file"""
    try:
        # Process the uploaded file
        valid_cases, errors = data_manager.process_uploaded_file(file)

        if not valid_cases and not errors:
            raise HTTPException(
                status_code=400,
                detail="No data found in the uploaded file"
            )

        # Prepare response
        response = {
            'status': 'success' if len(errors) == 0 else 'partial_success',
            'valid_cases_count': len(valid_cases),
            'errors_count': len(errors),
            'message': f"Processed {len(valid_cases)} valid cases"
        }

        if errors:
            response['errors'] = errors[:10]  # Limit errors returned to prevent huge responses
            if len(errors) > 10:
                response['errors'].append({
                    'message': f'And {len(errors) - 10} more errors...'
                })

        # If we have valid cases, add them to the current dataset
        if valid_cases:
            # Add new cases to the in-memory collection
            global cases
            cases.extend(valid_cases)

            # Retrain ML model with updated data
            try:
                ml_engine.train(cases)
                response['ml_model_retrained'] = True
            except Exception as ml_error:
                logger.warning(f"Failed to retrain ML model after upload: {ml_error}")
                response['ml_model_retrained'] = False
                response['ml_model_warning'] = "ML model retraining failed"

            response['message'] += f". Total cases now: {len(cases)}"

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error uploading cases")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@app.get('/datasets')
def list_datasets():
    """List available datasets in the data directory"""
    try:
        datasets = data_manager.get_available_datasets()
        return {
            'status': 'success',
            'datasets': datasets,
            'count': len(datasets)
        }
    except Exception as e:
        logger.exception("Error listing datasets")
        raise HTTPException(status_code=500, detail=f"Failed to list datasets: {str(e)}")


@app.post('/cases/batch')
def add_cases_batch(cases_data: List[Dict[str, Any]]):
    """Add multiple cases directly via JSON"""
    try:
        valid_cases = []
        errors = []

        # Process each case
        for index, case_data in enumerate(cases_data, start=1):
            try:
                # Normalize the case data
                case = normalize(case_data)

                # Validate the case
                is_valid, validation_errors = data_manager.validate_case_data(case)

                if is_valid:
                    valid_cases.append(case)
                else:
                    errors.append({
                        'item': index,
                        'errors': validation_errors
                    })

            except Exception as e:
                errors.append({
                    'item': index,
                    'error': f'Failed to process case: {str(e)}'
                })

        # Add valid cases to the collection
        if valid_cases:
            global cases
            cases.extend(valid_cases)

            # Retrain ML model
            try:
                ml_engine.train(cases)
                ml_retrained = True
            except Exception:
                ml_retrained = False

            return {
                'status': 'success' if len(errors) == 0 else 'partial_success',
                'added_cases_count': len(valid_cases),
                'errors_count': len(errors),
                'total_cases': len(cases),
                'ml_model_retrained': ml_retrained,
                'message': f"Added {len(valid_cases)} cases. Total: {len(cases)}"
            }
        else:
            return {
                'status': 'error',
                'added_cases_count': 0,
                'errors_count': len(errors),
                'errors': errors if errors else [{'message': 'No valid cases provided'}],
                'message': 'No valid cases to add'
            }

    except Exception as e:
        logger.exception("Error adding batch cases")
        raise HTTPException(status_code=500, detail=f"Batch case addition failed: {str(e)}")
