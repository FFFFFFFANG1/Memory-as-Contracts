def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls and not traj:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No trajectory or tool calls found', 'evidence_refs': []}
    # Count advanced_calculator total
    adv_count = sum(1 for tc in tool_calls if (tc.get('name') or '') == 'advanced_calculator')
    if adv_count > 5:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'advanced_calculator called {adv_count} times, exceeds max 5', 'evidence_refs': ['tool_calls']}
    # Check each assistant turn for >=6 distinct tools called in parallel
    turns_checked = 0
    for step in traj:
        tcs = step.get('tool_calls') or []
        if not tcs:
            continue
        turns_checked += 1
        names = set()
        for tc in tcs:
            n = tc.get('name') or (tc.get('function') or {}).get('name')
            if n:
                names.add(n)
        if len(names) < 6:
            return {'observed_followed': False, 'confidence': 'high', 'reason': f'Turn has only {len(names)} distinct tools in parallel, need >=6', 'evidence_refs': ['trajectory']}
    if turns_checked == 0:
        # Fallback: group flattened tool_calls by iteration
        groups = {}
        for tc in tool_calls:
            it = tc.get('iteration')
            if it is None:
                continue
            groups.setdefault(it, set()).add(tc.get('name'))
        if not groups:
            return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'Cannot determine per-turn parallel structure', 'evidence_refs': []}
        for it, names in groups.items():
            if len(names) < 6:
                return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Iteration {it} has {len(names)} distinct tools, need >=6', 'evidence_refs': ['tool_calls']}
        return {'observed_followed': True, 'confidence': 'medium', 'reason': f'All iterations have >=6 distinct tools; advanced_calculator used {adv_count} times', 'evidence_refs': ['tool_calls']}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'All {turns_checked} turn(s) used >=6 distinct parallel tools; advanced_calculator used {adv_count} times (<=5)', 'evidence_refs': ['trajectory']}
