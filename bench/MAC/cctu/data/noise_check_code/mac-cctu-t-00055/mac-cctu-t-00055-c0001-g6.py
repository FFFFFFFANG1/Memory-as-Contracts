def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls to assess.', 'evidence_refs': []}
    if len(calls) < 2:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Only one tool call; no corroboration possible before any downstream use.', 'evidence_refs': [{'index': calls[0].get('index')}]}
    # Count calls per tool name in order
    seen_counts = {}
    violations = []
    # A 'downstream' call is any call after the first; require that prior to call i, the tool used at some earlier step j<i has been called at least twice (corroborated) before its output feeds i.
    # Heuristic: for each call after the first, check that the immediately preceding distinct tool has appeared >=2 times before this call.
    for i, c in enumerate(calls):
        name = c.get('name')
        seen_counts[name] = seen_counts.get(name, 0) + 1
        if i == 0:
            continue
        prev_names = [calls[j].get('name') for j in range(i)]
        # find last distinct prior tool different from current
        prior_distinct = None
        for pn in reversed(prev_names):
            if pn != name:
                prior_distinct = pn
                break
        if prior_distinct is None:
            continue
        prior_count = sum(1 for pn in prev_names if pn == prior_distinct)
        if prior_count < 2:
            violations.append({'index': c.get('index'), 'name': name, 'uncorroborated_upstream': prior_distinct, 'upstream_count': prior_count})
    if violations:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Found {len(violations)} downstream call(s) whose upstream tool was not corroborated by a second call before use.', 'evidence_refs': violations[:5]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Each downstream tool call was preceded by at least two calls to its upstream tool, indicating corroboration.', 'evidence_refs': []}
