def evaluate(trace):
    import re
    allowed = 'bank_failure_analyzer'
    forbidden_used = []
    used_allowed = False
    for tc in trace.get('tool_calls', []) or []:
        name = tc.get('name')
        if name == allowed:
            used_allowed = True
        elif name:
            forbidden_used.append(name)
    final = (trace.get('final_response') or '').strip()
    if forbidden_used:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Used non-allowed tools: {sorted(set(forbidden_used))}', 'evidence_refs': []}
    if not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response to assess CSV format', 'evidence_refs': []}
    # Take first non-empty line as the CSV row candidate
    lines = [l.strip() for l in final.splitlines() if l.strip()]
    if not lines:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Empty final response', 'evidence_refs': []}
    # Accept if any line is a CSV row with exactly 3 fields and middle field looks like a year
    import csv, io
    ok = False
    for line in lines:
        try:
            row = next(csv.reader(io.StringIO(line)))
        except Exception:
            continue
        if len(row) == 3 and re.fullmatch(r'\s*\d{3,4}\s*', row[1] or ''):
            ok = True
            break
    if ok:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'Final response contains a 3-field CSV row with year in middle field', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Final response is not a CSV row of institution,year,jurisdiction', 'evidence_refs': []}
