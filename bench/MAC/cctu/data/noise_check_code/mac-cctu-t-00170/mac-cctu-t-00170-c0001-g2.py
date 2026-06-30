def evaluate(trace):
    traj = trace.get('trajectory') or []
    turns = []
    for step in traj:
        tcs = step.get('tool_calls') or []
        if tcs:
            turns.append// 0
    # Rebuild properly
    turns = [s.get('tool_calls') or [] for s in traj if (s.get('tool_calls') or [])]
    if not turns:
        tcs = trace.get('tool_calls') or []
        if not tcs:
            return {'observed_followed': None, 'confidence':'unknown','reason':'No tool calls found','evidence_refs':[]}
        by_iter = {}
        for c in tcs:
            k = c.get('iteration', c.get('index'))
            by_iter.setdefault(k, []).append(c)
        turns = [by_iter[k] for k in sorted(by_iter.keys(), key=lambda x:(x is None,x))]
    total_turns = len(turns)
    issues = []
    for i,t in enumerate(turns):
        names = {c.get('name') for c in t if c.get('name')}
        if len(names) < 5:
            issues.append(f'turn {i+1} had {len(names)} unique tools')
    if total_turns > 4:
        issues.append(f'total turns {total_turns} > 4')
    followed = len(issues) == 0
    return {'observed_followed': followed, 'confidence': 'high' if followed or issues else 'low', 'reason': '; '.join(issues) if issues else f'{total_turns} turns, each with >=5 unique tools', 'evidence_refs': []}
