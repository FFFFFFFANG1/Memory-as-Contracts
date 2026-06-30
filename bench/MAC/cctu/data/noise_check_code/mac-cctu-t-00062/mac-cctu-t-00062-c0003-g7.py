def evaluate(trace):
    import re
    final = (trace.get('final_response') or '')
    traj = trace.get('trajectory') or []
    # Gather user messages to detect explicit provenance request
    user_text = ''
    for step in traj:
        role = step.get('role') if isinstance(step, dict) else None
        if role == 'user':
            c = step.get('content') or ''
            if isinstance(c, list):
                c = ' '.join(str(x) for x in c)
            user_text += '\n' + str(c)
    if not user_text:
        # fallback: check trace-level user field
        user_text = str(trace.get('user_query') or '')
    prov_patterns = [r'provenance', r'source', r'origin', r'where .* (from|come)', r'cite', r'citation', r'dataset', r'reference']
    explicit = any(re.search(p, user_text, re.I) for p in prov_patterns)
    if not explicit:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No explicit user request for source provenance detected; constraint not triggered.', 'evidence_refs': []}
    text = final.lower()
    has_confidence = any(k in text for k in ['confidence', 'disclaimer', 'caveat', 'uncertain', 'limitation'])
    has_dataset_version = bool(re.search(r'(dataset|data set|version|v\d|release|edition)', text, re.I))
    if has_confidence and has_dataset_version:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Final response includes a confidence/disclaimer mention and cites a dataset version.', 'evidence_refs': ['final_response']}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Provenance requested but final lacks confidence_disclaimer={has_confidence} or dataset_version={has_dataset_version}.', 'evidence_refs': ['final_response']}
