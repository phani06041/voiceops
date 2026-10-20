import csv
import logging
from pathlib import Path
from typing import Any, List, Dict
from app.config import DATA_DIR
from app.services.ml_engine import ml_engine

logger = logging.getLogger(__name__)

CANONICAL = [
    'case_id', 'domain', 'exception_text', 'status', 'suggested_action',
    'manual_review_required', 'exception_type', 'confidence_score',
    'sensitive_case', 'missing_fields', 'supporting_evidence', 'authorization_type'
]
ALIASES = {
    'expected_action': 'suggested_action',
    'recommended_action': 'suggested_action',
    'approved_resolution': 'suggested_action',
    'expected_type': 'exception_type',
    'case_status': 'status',
    'review_queue_status': 'manual_review_required',
    'Review Queue Status': 'manual_review_required',
    'authorizationType': 'authorization_type'
}

def _bool(value: Any) -> bool:
    if isinstance(value, bool): return value
    return str(value or '').strip().lower() in {'true', '1', 'yes', 'y', 'review'}

def normalize(row: dict[str, Any], fallback_domain: str | None = None) -> dict[str, Any]:
    data = {ALIASES.get(k, k): v for k, v in row.items()}
    for field in CANONICAL:
        data.setdefault(field, '')
    data['case_id'] = str(data['case_id'] or '').strip()
    data['domain'] = str(data['domain'] or fallback_domain or '').strip().lower()
    data['exception_text'] = str(data['exception_text'] or '').strip()
    data['exception_type'] = str(data['exception_type'] or 'unknown').strip().lower()
    data['suggested_action'] = str(data['suggested_action'] or 'abstain').strip().lower()
    data['status'] = str(data['status'] or 'new').strip().lower().replace(' ', '_')
    data['authorization_type'] = str(data['authorization_type'] or '').strip().upper()
    if data['authorization_type'] not in {'PRE', 'POST', ''}:
        data['authorization_type'] = 'UNKNOWN'
    data['sensitive_case'] = _bool(data['sensitive_case'])
    data['manual_review_required'] = _bool(data['manual_review_required'])
    try:
        data['confidence_score'] = max(0.0, min(1.0, float(data['confidence_score']))) if str(data['confidence_score']).strip() else 0.5
    except (ValueError, TypeError):
        data['confidence_score'] = 0.5

    raw_missing = data.get('missing_fields', '')
    if isinstance(raw_missing, list):
        data['missing_fields'] = raw_missing
    else:
        data['missing_fields'] = [x.strip() for x in str(raw_missing or '').split(';') if x.strip()]

    data['supporting_evidence'] = str(data['supporting_evidence'] or '').strip()

    # Backwards compatibility mirrors
    data['expected_type'] = data['exception_type']
    data['expected_action'] = data['suggested_action']
    data['review_queue_status'] = data['manual_review_required']
    data['evidence_references'] = []
    data['document_type'] = ''

    return data

def load_cases(data_dir: Path | None = None) -> tuple[list[dict], list[dict]]:
    directory = data_dir or DATA_DIR
    cases, issues, seen = [], [], set()
    for filename in ['open_cases.csv', 'approved_cases.csv', 'mortgage_cases.csv']:
        path = directory / filename
        if not path.exists():
            if filename == 'mortgage_cases.csv': continue
            issues.append({'file': filename, 'row': 0, 'error': 'File not found'})
            continue
        try:
            with path.open('r', encoding='utf-8-sig', newline='') as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames:
                    issues.append({'file': filename, 'row': 1, 'error': 'Missing CSV header'}); continue
                for n, row in enumerate(reader, start=2):
                    try:
                        case = normalize(row)
                        if not case['case_id'] or not case['exception_text'] or case['domain'] not in {'mortgage','healthcare'}:
                            raise ValueError('case_id, exception_text, or supported domain missing')
                        if case['case_id'] in seen:
                            issues.append({'file': filename, 'row': n, 'error': f"Duplicate case_id: {case['case_id']}"}); continue
                        seen.add(case['case_id']); case['_source_file'] = filename; cases.append(case)
                    except Exception as e: issues.append({'file': filename, 'row': n, 'error': str(e)})
        except OSError as e: issues.append({'file': filename, 'row': 0, 'error': str(e)})
    # Existing sample files are healthcare-only. Add small, explicitly synthetic mortgage examples only when none are provided.
    if not any(c['domain'] == 'mortgage' for c in cases):
        samples = [
          ('MTG-SYN-001','The latest pay stub is missing from the mortgage application.','missing_document',['latest_pay_stub'],False,0.96,'Synthetic demo: document checklist marks latest pay stub as not received.'),
          ('MTG-SYN-002','Applicant name differs between the application and supporting document.','field_mismatch',[],False,0.71,'Synthetic demo: source values disagree; reviewer must verify authoritative value.'),
          ('MTG-SYN-003','Income figures conflict across supplied documents and may require investigation.','suspicious_discrepancy',[],True,0.38,'Synthetic demo: conflicting figures require investigation; this is not a fraud finding.')]
        for cid, text, typ, missing, sensitive, conf, evidence in samples:
            cases.append(normalize({'case_id':cid,'domain':'mortgage','exception_text':text,'expected_type':typ,'status':'open','sensitive_case':sensitive,'missing_fields':';'.join(missing),'confidence_score':conf,'review_queue_status':sensitive or conf < .65,'supporting_evidence':evidence}))
            cases[-1]['_source_file'] = 'synthetic_demo'

    # Train ML model on loaded cases
    try:
        ml_engine.train(cases)
        logger.info("ML model training completed during data loading")
    except Exception as e:
        logger.warning(f"ML model training failed during data loading: {e}")

    return cases, issues
