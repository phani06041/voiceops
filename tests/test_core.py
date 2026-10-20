from app.services.data_loader import normalize
from app.services.exception_engine import process
from app.services.query_engine import answer

def case(**kwargs):
    base={'case_id':'X1','domain':'healthcare','exception_text':'The clinical note is missing.','expected_type':'missing_clinical_document','status':'open','authorization_type':'PRE','missing_fields':['clinical_note'],'evidence_references':['doc1'],'supporting_evidence':'Checklist says not received.','confidence_score':0.98,'sensitive_case':False,'manual_review_required':False}
    base.update(kwargs); return normalize(base)

def test_normalize_booleans_and_fields():
    c=normalize({'case_id':'A','domain':'healthcare','exception_text':' x ','sensitive_case':'yes','missing_fields':'a;b','confidence_score':'1.2'})
    assert c['sensitive_case'] is True and c['missing_fields']==['a','b'] and c['confidence_score']==1

def test_healthcare_missing_document():
    r=process(case()); assert r['recommended_action']=='request_missing_document'; assert 'clinical_note' in r['missing_fields']

def test_sensitive_case_abstains_even_high_confidence():
    r=process(case(sensitive_case=True,confidence_score=0.99)); assert r['recommended_action']=='abstain' and r['manual_review_required']

def test_unknown_auth_routes_to_specialist():
    r=process(case(authorization_type='UNKNOWN',missing_fields=[])); assert r['recommended_action']=='route_to_specialist' and r['manual_review_required']

def test_mortgage_separate_rules():
    r=process(case(domain='mortgage',exception_text='Latest pay stub is missing.',missing_fields=['latest_pay_stub'])); assert r['recommended_action']=='request_missing_document'

def test_query_uses_real_case():
    c=case(); r=answer('what is missing?', [c], 'X1'); assert 'clinical_note' in r['answer'] and r['case_id']=='X1'

def test_query_unknown_case_does_not_invent():
    r=answer('what is missing?', [case()], 'NOPE'); assert 'not found' in r['answer']

def test_resolved_case_syncs_close_action_and_no_review():
    r=process(case(status='resolved',exception_text='The clinical note was missing.')); assert r['recommended_action']=='close_case' and not r['manual_review_required'] and r['review_queue_status']=='Resolved'

def test_pending_document_syncs_await_action_and_no_review():
    r=process(case(status='pending_document',missing_fields=['w2_form'])); assert r['recommended_action']=='await_document_submission' and not r['manual_review_required'] and r['review_queue_status']=='Awaiting Doc'

def test_pending_specialist_syncs_specialist_action_and_review():
    r=process(case(status='pending_specialist')); assert r['recommended_action']=='route_to_specialist' and r['manual_review_required'] and r['review_queue_status']=='Review Needed'

