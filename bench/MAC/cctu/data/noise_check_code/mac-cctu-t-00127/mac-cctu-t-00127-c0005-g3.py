def evaluate(trace):
    calls = trace.get('tool_calls') or []
    target = 'aircraft_specifications_retriever'
    spec_calls = [c for c in calls if c.get('name') == target]
    if not spec_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no aircraft_specifications_retriever calls', 'evidence_refs': []}
    iters = {}
    for c in calls:
        it = c.get('iteration')
        if it is None:
            continue
        iters.setdefault(it, []).append(c)
    violations = []
    for it, group in iters.items():
        names = [g.get('name') for g in group]
        if names.count(target) > 1:
            violations.append({'iteration': it, 'issue': 'parallel aircraft spec calls', 'names': names})
        elif target in names and len(group) > 1:
            violations.append({'iteration': it, 'issue': 'aircraft spec parallel with other tool', 'names': names})
    if violations:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'aircraft_specifications_retriever invoked in parallel', 'evidence_refs': violations[:3]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'aircraft spec retrievals issued one at a time', 'evidence_refs': [{'count': len(spec_calls)}]}
