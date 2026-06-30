def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls found', 'evidence_refs': []}
    groups = {}
    for c in calls:
        key = c.get('iteration')
        if key is None:
            key = c.get('turn')
        if key is None:
            key = c.get('step')
        groups.setdefault(key, []).append(c)
    if len(groups) == 1 and list(groups.keys())[0] is None:
        # fallback: treat whole trajectory as one turn
        first = calls[0]
        ok = (first.get('name') == 'philosopher_identifier')
        return {'observed_followed': ok, 'confidence': 'low', 'reason': f'single-group fallback; first tool={first.get("name")}', 'evidence_refs': [first.get('name')]}
    bad = []
    for k, lst in groups.items():
        lst_sorted = sorted(lst, key=lambda x: x.get('index', 0))
        first = lst_sorted[0]
        if first.get('name') != 'philosopher_identifier':
            bad.append({'turn': k, 'first_tool': first.get('name')})
    if bad:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'{len(bad)} turn(s) did not begin with philosopher_identifier', 'evidence_refs': bad}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'each turn began with philosopher_identifier', 'evidence_refs': list(groups.keys())}
