def evaluate(trace):
    from collections import Counter
    trajectory = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    if not trajectory and not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no trajectory or tool calls available', 'evidence_refs': []}
    reasons = []
    # interaction turns: count steps that have tool_calls or are assistant steps
    turns = []
    for step in trajectory:
        tcs = step.get('tool_calls') if isinstance(step, dict) else None
        if tcs:
            turns.append(tcs)
    round_count = len(turns) if turns else len(trajectory)
    if round_count < 2:
        reasons.append('interaction rounds ' + str(round_count) + ' below 2')
    if round_count > 8:
        reasons.append('interaction rounds ' + str(round_count) + ' above 8')
    # total tool calls <=5
    total = len(tool_calls)
    if total > 5:
        reasons.append('total tool calls ' + str(total) + ' exceeds 5')
    # each individual tool <=3
    per_tool = Counter()
    for tc in tool_calls:
        name = tc.get('name') if isinstance(tc, dict) else None
        if name:
            per_tool[name] += 1
    for n, c in per_tool.items():
        if c > 3:
            reasons.append('tool ' + str(n) + ' called ' + str(c) + ' times (>3)')
    # <=2 unique tool types per turn
    for i, tcs in enumerate(turns):
        names = set()
        for tc in tcs:
            nm = tc.get('name') if isinstance(tc, dict) else (tc.get('function', {}).get('name') if isinstance(tc, dict) else None)
            if nm:
                names.add(nm)
        if len(names) > 2:
            reasons.append('turn ' + str(i) + ' uses ' + str(len(names)) + ' unique tools (>2)')
    if reasons:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'turn count, total calls, per-tool calls, and per-turn unique tools within limits', 'evidence_refs': []}
