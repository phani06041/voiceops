from app.config import CONFIDENCE_REVIEW_THRESHOLD
from app.rules import mortgage_rules, healthcare_rules
from app.services.ml_engine import ml_engine

def process(case: dict) -> dict:
    domain = case.get('domain')
    if domain == 'mortgage': result = mortgage_rules.evaluate(case)
    elif domain == 'healthcare': result = healthcare_rules.evaluate(case)
    else: result = {'exception_type':'unknown_domain','recommended_action':'abstain','manual_review_required':True,'review_reason':'Unsupported or missing domain.'}

    # ML augmentation: get ML prediction and combine with rule-based result
    ml_exception_type, ml_confidence = ml_engine.predict(case)

    # ML enhancement logic:
    # 1. Very high confidence ML prediction (>0.85) enhances any rule-based result
    # 2. Good confidence ML prediction (>0.70) enhances uncertain/unknown results
    use_ml_prediction = False
    if ml_engine.is_trained and ml_exception_type is not None:
        if ml_confidence > 0.85:
            # Very high confidence - enhance any result
            use_ml_prediction = True
        elif ml_confidence > 0.70 and result['exception_type'] in ['uncertain_exception', 'unknown_domain']:
            # Good confidence - enhance only uncertain results
            use_ml_prediction = True

    if use_ml_prediction:
        # Use ML prediction but keep rule-based action logic
        final_exception_type = ml_exception_type
        ml_enhanced = True
        if ml_confidence > 0.85:
            review_reason = f"ML-enhanced prediction (high confidence): {ml_exception_type} (confidence: {ml_confidence:.2f}). {result['review_reason']}"
        else:
            review_reason = f"ML-enhanced prediction: {ml_exception_type} (confidence: {ml_confidence:.2f}). {result['review_reason']}"
    else:
        final_exception_type = result['exception_type']
        ml_enhanced = False
        review_reason = result['review_reason']

    status = str(case.get('status', 'new')).lower().strip().replace(' ', '_')
    if status in {'resolved', 'closed'}:
        review = False
        action = result['recommended_action']
    elif status == 'pending_document':
        review = False
        action = result['recommended_action']
    else:
        review = bool(result['manual_review_required'] or case.get('manual_review_required') or case.get('sensitive_case') or case.get('confidence_score', 0.5) < CONFIDENCE_REVIEW_THRESHOLD)
        action = result['recommended_action']
        if case.get('sensitive_case'):
            action = 'abstain'

    evidence = [x for x in [case.get('exception_text'), case.get('supporting_evidence')] if x]
    if case.get('evidence_references'):
        evidence += [f"Source reference: {x}" for x in case.get('evidence_references', [])]
    explanation = review_reason
    if case.get('missing_fields'):
        explanation += ' Missing: ' + ', '.join(case['missing_fields']) + '.'

    if status == 'resolved':
        rq_status = 'Resolved'
    elif status == 'closed':
        rq_status = 'Closed'
    elif status == 'pending_document':
        rq_status = 'Awaiting Doc'
    elif review:
        rq_status = 'Review Needed'
    else:
        rq_status = 'Automated'

    return {
        'case_id':case.get('case_id'),
        'domain':domain,
        'exception_type':final_exception_type,
        'recommended_action':action,
        'explanation':explanation,
        'supporting_evidence':evidence,
        'missing_fields':case.get('missing_fields',[]),
        'confidence_score':case.get('confidence_score',0.5),
        'confidence_is_heuristic':True,
        'ml_enhanced':ml_enhanced,
        'ml_confidence':ml_confidence if ml_enhanced else None,
        'ml_predicted_type':ml_exception_type if ml_enhanced else None,
        'manual_review_required':review,
        'review_queue_status':rq_status,
        'review_reason':review_reason,
        'status':case.get('status','new')
    }
