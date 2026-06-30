def evaluate(trace):
    allowed = {'landmark_identifier','cultural_landmark_identifier'}
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls found', 'evidence_refs': []}
    names = [c.get('name') for c in calls]
    first = names[0]
    if first not in allowed:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'first tool call was {first}, not a scoping tool', 'evidence_refs': [{'index': 0, 'name': first}]}
    scoping_done = False
    for i, n in enumerate(names):
        if n in allowed:
            scoping_done = True
            continue
        if not scoping_done:
            return {'observed_followed': False, 'confidence': 'high', 'reason': f'enrichment tool {n} called before scoping with allowed tools', 'evidence_refs': [{'index': i, 'name': n}]}
        else:
            break
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'preliminary scoping used only landmark_identifier/cultural_landmark_identifier before other tools', 'evidence_refs': [{'first_calls': names[:3]}]}
