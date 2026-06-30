def evaluate(trace):
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls observed', 'evidence_refs': []}
    violations = []
    checked = 0
    for tc in tool_calls:
        args = tc.get('arguments')
        if not isinstance(args, dict):
            continue
        if 'query' not in args:
            continue
        q = args.get('query')
        if not isinstance(q, str):
            continue
        checked += 1
        if len(q) >= 80:
            violations.append({'index': tc.get('index'), 'tool': tc.get('name'), 'length': len(q)})
    if checked == 0:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls with query parameter found', 'evidence_refs': []}
    if violations:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'query parameter >=80 chars in ' + str(len(violations)) + ' call(s)', 'evidence_refs': violations}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'all ' + str(checked) + ' query parameters under 80 characters', 'evidence_refs': []}
