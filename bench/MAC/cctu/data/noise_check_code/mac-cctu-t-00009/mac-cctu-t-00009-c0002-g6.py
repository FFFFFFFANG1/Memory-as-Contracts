def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls present', 'evidence_refs': []}
    date_re = re.compile(r'\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}|\b\d{4}\b)')
    date_to_tools = {}
    for tc in tool_calls:
        name = tc.get('name') or ''
        blob = ''
        for k in ('arguments','result'):
            v = tc.get(k)
            if v is not None:
                blob += ' ' + (v if isinstance(v,str) else str(v))
        for d in set(date_re.findall(blob)):
            date_to_tools.setdefault(d, set()).add(name)
    if not date_to_tools:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No candidate dates detected in tool I/O', 'evidence_refs': []}
    insufficient = [d for d,ts in date_to_tools.items() if len(ts) < 2]
    full_text = (trace.get('final_response') or '')
    for step in (trace.get('trajectory') or []):
        c = step.get('content')
        if c: full_text += '\n' + (c if isinstance(c,str) else str(c))
    log_terms = ['verification log','agreement','disagree','agree','cross-check','corroborat','conflict','match','mismatch']
    has_log = any(t.lower() in full_text.lower() for t in log_terms)
    if insufficient:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Dates queried via <2 tools: {insufficient[:5]}', 'evidence_refs': []}
    if not has_log:
        return {'observed_followed': False, 'confidence': 'low', 'reason': 'No verification log of agreement/disagreement found', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'All detected dates queried via >=2 tools and verification log terms present', 'evidence_refs': []}
