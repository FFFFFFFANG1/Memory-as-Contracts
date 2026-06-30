def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls', 'evidence_refs': []}
    turns = {}
    for c in calls:
        it = c.get('iteration')
        turns.setdefault(it, set()).add(c.get('name'))
    paired = False
    botanist_seen = False
    evidence = []
    for it, names in turns.items():
        if 'botanist_research_locator' in names:
            botanist_seen = True
            if 'individual_locator' in names:
                paired = True
                evidence.append({'iteration': it, 'tools': sorted(list(names))})
                break
    if paired:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'botanist_research_locator paired with individual_locator in same turn', 'evidence_refs': evidence}
    if not botanist_seen:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'botanist_research_locator never invoked', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'high', 'reason': 'botanist_research_locator invoked but not paired with individual_locator in same turn', 'evidence_refs': []}
