def evaluate(trace):
    target = {'continent_locator','rainforest_info_provider','sports_event_locator'}
    traj = trace.get('trajectory') or []
    found_turn = None
    for i, step in enumerate(traj):
        calls = step.get('tool_calls') or []
        names = [c.get('name') for c in calls]
        if target.issubset(set(names)):
            found_turn = i
            break
    if found_turn is not None:
        return {'observed_followed': True, 'confidence':'high','reason':'All three lookups batched in one turn','evidence_refs':[{'turn':found_turn}]}
    # check if any of the three were called at all
    tc = trace.get('tool_calls') or []
    used = [c for c in tc if c.get('name') in target]
    if not used:
        return {'observed_followed': None,'confidence':'unknown','reason':'No relevant lookups observed','evidence_refs':[]}
    # they were called but not batched in one turn
    by_iter = {}
    for c in used:
        key = c.get('iteration', c.get('index'))
        by_iter.setdefault(key, set()).add(c.get('name'))
    batched = any(target.issubset(v) for v in by_iter.values())
    if batched:
        return {'observed_followed': True,'confidence':'medium','reason':'All three appear in same iteration','evidence_refs':[]}
    return {'observed_followed': False,'confidence':'high','reason':'Lookups were split across turns/iterations','evidence_refs':[{'iterations':list(by_iter.keys())}]}
