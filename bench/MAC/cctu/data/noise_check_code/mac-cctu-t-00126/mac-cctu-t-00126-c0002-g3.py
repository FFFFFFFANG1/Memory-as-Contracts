def evaluate(trace):
    calls = trace.get('tool_calls', []) or []
    final = (trace.get('final_response') or '').strip()
    if not calls and not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No trajectory data', 'evidence_refs': []}
    n = len(calls)
    distinct = {c.get('name') for c in calls if c.get('name')}
    ends_ok = final.rstrip().rstrip('"\'').endswith('Verified across multiple sources.')
    reasons = []
    ok = True
    if n < 4:
        ok = False; reasons.append(f'only {n} tool calls (<4)')
    if len(distinct) < 3:
        ok = False; reasons.append(f'only {len(distinct)} distinct tools (<3)')
    if not ends_ok:
        ok = False; reasons.append('final response does not end with required phrase')
    return {'observed_followed': ok, 'confidence': 'high' if ok else 'medium', 'reason': 'ok' if ok else '; '.join(reasons), 'evidence_refs': []}
