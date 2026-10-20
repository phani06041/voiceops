from app.services.exception_engine import process

def answer(question: str, cases: list[dict], case_id: str | None = None) -> dict:
    q = question.strip().lower()
    if case_id:
        found = next((c for c in cases if c['case_id'].lower() == case_id.lower()), None)
        if not found: return {'answer':f'Case {case_id} was not found in the loaded dataset.','case_id':case_id,'evidence':[],'recommended_action':None,'requires_review':False}
        r = process(found)
        if any(k in q for k in ['missing','document']): msg = 'Missing information: ' + (', '.join(r['missing_fields']) if r['missing_fields'] else 'No structured missing-field list is recorded. Check the exception description and evidence below.')
        elif any(k in q for k in ['next','should happen','action','what should']): msg = f"Recommended next action: {r['recommended_action']}. {r['explanation']}"
        elif any(k in q for k in ['evidence','support']): msg = 'Supporting evidence: ' + (' '.join(r['supporting_evidence']) or 'No supporting evidence was supplied.')
        else: msg = f"Case {found['case_id']} is {found['status']}. {r['explanation']} Recommended action: {r['recommended_action']}."
        return {'answer':msg,'case_id':found['case_id'],'evidence':r['supporting_evidence'],'recommended_action':r['recommended_action'],'requires_review':r['manual_review_required']}
    filtered = cases
    if 'human review' in q or 'manual review' in q or 'specialist' in q: filtered = [c for c in cases if process(c)['manual_review_required']]
    elif 'healthcare' in q: filtered = [c for c in cases if c['domain']=='healthcare']
    elif 'mortgage' in q: filtered = [c for c in cases if c['domain']=='mortgage']
    if 'pre' in q and 'healthcare' in q: filtered = [c for c in filtered if c['authorization_type']=='PRE']
    if 'post' in q and 'healthcare' in q: filtered = [c for c in filtered if c['authorization_type']=='POST']
    if not filtered: msg = 'No matching cases were found in the currently loaded dataset.'
    else: msg = f"Found {len(filtered)} matching case(s): " + ', '.join(f"{c['case_id']} ({c['domain']}, {c['status']})" for c in filtered[:25]) + ('.' if len(filtered)<=25 else f" … and {len(filtered)-25} more.")
    return {'answer':msg,'case_id':None,'evidence':[],'recommended_action':None,'requires_review':any(process(c)['manual_review_required'] for c in filtered)}
