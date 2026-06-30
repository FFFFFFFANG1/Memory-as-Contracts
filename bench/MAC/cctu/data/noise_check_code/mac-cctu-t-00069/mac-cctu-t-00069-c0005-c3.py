def evaluate(trace):
    import re
    allowed = {'island_beach_finder','oasis_feature_locator'}
    calls = trace.get('tool_calls') or []
    used = [c.get('name') for c in calls if c.get('name')]
    forbidden_used = [n for n in used if n not in allowed]
    final = (trace.get('final_response') or '').strip()
    if not final:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    paragraphs = [p for p in re.split(r'\n\s*\n', final) if p.strip()]
    two_paragraphs = len(paragraphs) == 2
    if forbidden_used:
        return {'observed_followed': False,'confidence':'high','reason': f'used disallowed tools: {forbidden_used}','evidence_refs': forbidden_used}
    if not two_paragraphs:
        return {'observed_followed': False,'confidence':'high','reason': f'expected 2 paragraphs, found {len(paragraphs)}','evidence_refs': []}
    return {'observed_followed': True,'confidence':'high','reason':'only allowed tools used and response is two paragraphs','evidence_refs': used}
