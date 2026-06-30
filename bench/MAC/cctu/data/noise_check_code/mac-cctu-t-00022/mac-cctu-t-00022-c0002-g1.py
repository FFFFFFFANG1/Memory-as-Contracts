def evaluate(trace):
    import re
    allowed = 'space_mission_identifier'
    forbidden = ['disaster_event_info','election_result_analyzer','election_result_finder','financial_event_identifier','political_term_tracker']
    calls = trace.get('tool_calls') or []
    used = [c.get('name') for c in calls]
    bad = [n for n in used if n in forbidden]
    if bad:
        return {'observed_followed': False, 'confidence':'high','reason': f'used forbidden tools: {bad}','evidence_refs':[]}
    resp = trace.get('final_response') or ''
    if not resp.strip():
        return {'observed_followed': None,'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    lines = [l for l in resp.splitlines() if l.strip()]
    numbered = [l for l in lines if re.match(r'^\s*\d+[\.)]\s+', l)]
    if len(numbered) < 1:
        return {'observed_followed': False,'confidence':'high','reason':'no numbered list detected','evidence_refs':[]}
    bold_in_numbered = [l for l in numbered if re.search(r'\*\*[^*]+\*\*', l) or re.search(r'__[^_]+__', l)]
    if len(bold_in_numbered) < len(numbered):
        return {'observed_followed': False,'confidence':'medium','reason':'not all numbered items have bold text','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'high','reason':'tool usage restricted and response is numbered list with bold names','evidence_refs':[]}
