def evaluate(trace):
    import re
    calls = trace.get('tool_calls', []) or []
    names = [c.get('name','') for c in calls]
    if not names:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls observed', 'evidence_refs': []}
    forbidden = {'historical_incident_data_retriever','incident_info_retriever'}
    used_aviation = any(n == 'aviation_incident_database' for n in names)
    used_forbidden = [n for n in names if n in forbidden]
    final = (trace.get('final_response') or '').lower()
    # detect markdown table
    lines = (trace.get('final_response') or '').splitlines()
    has_table = False
    for i, ln in enumerate(lines):
        if '|' in ln and i+1 < len(lines) and re.search(r'\|\s*:?-{2,}', lines[i+1]):
            has_table = True
            break
    has_flight = 'flight' in final
    has_date = 'date' in final
    has_severity = 'severity' in final
    cols_ok = has_flight and has_date and has_severity
    if used_forbidden:
        return {'observed_followed': False, 'confidence':'high','reason': f'Used forbidden tools: {used_forbidden}','evidence_refs':[]}
    if not used_aviation:
        return {'observed_followed': False, 'confidence':'high','reason':'aviation_incident_database not used','evidence_refs':[]}
    if not has_table:
        return {'observed_followed': False, 'confidence':'medium','reason':'No markdown table detected','evidence_refs':[]}
    if not cols_ok:
        return {'observed_followed': False, 'confidence':'medium','reason':'Missing required columns (flight/date/severity)','evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'high','reason':'Exclusively used aviation_incident_database and produced markdown table with required columns','evidence_refs':[]}
