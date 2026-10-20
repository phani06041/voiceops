def evaluate(case: dict) -> dict:
    status = str(case.get('status', 'new')).lower().strip().replace(' ', '_')
    text = (case.get('exception_text', '') + ' ' + str(case.get('exception_type', '')) + ' ' + str(case.get('expected_type', '')) + ' ' + str(case.get('supporting_evidence', ''))).lower()

    # Lifecycle terminal & waiting status overrides
    if status == 'resolved':
        return {
            'exception_type': case.get('exception_type') or case.get('expected_type') or 'resolved_exception',
            'recommended_action': 'close_case',
            'manual_review_required': False,
            'review_reason': 'Healthcare exception has been verified and resolved. Ready for closure.'
        }
    if status == 'closed':
        return {
            'exception_type': case.get('exception_type') or case.get('expected_type') or 'closed_exception',
            'recommended_action': 'archived',
            'manual_review_required': False,
            'review_reason': 'Case is closed and archived.'
        }
    if status == 'pending_document':
        missing = case.get('missing_fields') or []
        missing_str = ', '.join(missing) if missing else 'required clinical documentation'
        return {
            'exception_type': 'missing_document',
            'recommended_action': 'await_document_submission',
            'manual_review_required': False,
            'review_reason': f'Awaiting receipt of missing clinical document(s): {missing_str}. Automated reminder active.'
        }
    if status == 'pending_specialist':
        return {
            'exception_type': case.get('exception_type') or case.get('expected_type') or 'low_confidence_extraction',
            'recommended_action': 'route_to_specialist',
            'manual_review_required': True,
            'review_reason': 'Escalated for clinical specialist or medical director review.'
        }

    # Active / In Review / New cases
    if case.get('sensitive_case') or any(k in text for k in ['suspected_fraud', 'potentially altered', 'suspicious billing', 'fraud', 'altered invoice']):
        return {
            'exception_type': 'suspicious_discrepancy',
            'recommended_action': 'abstain',
            'manual_review_required': True,
            'review_reason': 'Sensitive billing or document discrepancy requires authorized human investigation.'
        }
    if case.get('authorization_type') not in {'PRE', 'POST'}:
        return {
            'exception_type': case.get('exception_type') or case.get('expected_type') or 'uncertain_exception',
            'recommended_action': 'route_to_specialist',
            'manual_review_required': True,
            'review_reason': 'Authorization type is unknown or insufficiently supported.'
        }
    if case.get('missing_fields') or any(k in text for k in ['missing', 'not supplied', 'not received', 'absent']):
        is_in_review = (status == 'in_review')
        needs_review = is_in_review or bool(case.get('manual_review_required')) or (case.get('confidence_score', 0.5) < 0.8)
        return {
            'exception_type': 'missing_document',
            'recommended_action': 'request_missing_document',
            'manual_review_required': needs_review,
            'review_reason': 'Review in progress for missing clinical document.' if is_in_review else ('Required document is reported missing.' if case.get('missing_fields') else 'Verify the missing-document requirement against the source checklist.')
        }
    if any(k in text for k in ['mismatch', 'differs', 'disagree', 'inconsistent']):
        return {
            'exception_type': 'field_mismatch',
            'recommended_action': 'propose_field_correction',
            'manual_review_required': True,
            'review_reason': 'Conflicting source values require verification before correction.'
        }
    if case.get('confidence_score', 0.5) < 0.65:
        return {
            'exception_type': 'low_confidence_extraction',
            'recommended_action': 'route_to_specialist',
            'manual_review_required': True,
            'review_reason': 'Extraction confidence is below the configured review threshold.'
        }
    return {
        'exception_type': case.get('exception_type') or case.get('expected_type') or 'uncertain_exception',
        'recommended_action': 'route_to_specialist',
        'manual_review_required': True,
        'review_reason': 'No sufficiently supported automatic action rule matched.'
    }

