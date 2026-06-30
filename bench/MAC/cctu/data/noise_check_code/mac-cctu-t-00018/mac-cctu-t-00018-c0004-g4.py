def evaluate(trace):
    calls = trace.get('tool_calls') or []
    names = [c.get('name') for c in calls if c.get('name')]
    distinct = set(names)
    if not calls:
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'no tool calls recorded', 'evidence_refs': []}
    final = (trace.get('final_response') or '')
    # heuristic: evidence trail = mentions intermediate findings before conclusion
    import re
    has_trail = bool(re.search(r'(evidence|step\s*\d|intermediate|finding|source|according to|based on)', final, re.I)) and len(final.strip()) > 0
    trajectory = trace.get('trajectory') or []
    # also accept evidence documented in assistant intermediate steps
    intermediate_text = ''
    for s in trajectory[:-1] if len(trajectory)>1 else []:
        intermediate_text += (s.get('content') or '') + '\n'
    has_intermediate_doc = len(intermediate_text.strip()) > 50
    enough_tools = len(distinct) >= 3
    followed = enough_tools and (has_trail or has_intermediate_doc)
    reason = f'distinct_tools={sorted(distinct)}, has_trail={has_trail}, has_intermediate_doc={has_intermediate_doc}'
    return {'observed_followed': bool(followed), 'confidence': 'high' if enough_tools else 'medium', 'reason': reason, 'evidence_refs': []}
