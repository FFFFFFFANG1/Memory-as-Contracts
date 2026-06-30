def evaluate(trace):
    import re
    allowed = 'international_organization_event_tracker'
    calls = trace.get('tool_calls') or []
    used = [c.get('name') for c in calls if c.get('name')]
    if not used:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls observed', 'evidence_refs': []}
    forbidden = [n for n in used if n != allowed]
    if forbidden:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'used non-allowed tools: {sorted(set(forbidden))}', 'evidence_refs': forbidden}
    final = trace.get('final_response') or ''
    if not final.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty final response', 'evidence_refs': []}
    # Try to extract a list of delegations: lines that look like list items
    lines = final.splitlines()
    items = []
    for ln in lines:
        m = re.match(r'\s*(?:[-*\u2022]|\d+[.)])\s+(.+?)\s*$', ln)
        if m:
            items.append(m.group(1).strip())
    if len(items) < 2:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'could not detect an enumerated delegation list', 'evidence_refs': []}
    norm = [re.sub(r'^["\'\(\[]+', '', it).strip().lower() for it in items]
    sorted_norm = sorted(norm)
    if norm == sorted_norm:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'delegations enumerated alphabetically and only allowed tool used', 'evidence_refs': items}
    return {'observed_followed': False, 'confidence': 'high', 'reason': 'delegations not in alphabetical order', 'evidence_refs': items}
