def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls found', 'evidence_refs': []}
    allowed = {'cultural_geography_locator', 'entity_location_finder'}
    deferred = {'choreographer_finder', 'local_band_finder', 'music_origin_identifier'}
    names = [c.get('name') for c in calls]
    # Find earliest index of any allowed scoping tool and any deferred tool
    first_allowed_idx = next((i for i,n in enumerate(names) if n in allowed), None)
    first_deferred_idx = next((i for i,n in enumerate(names) if n in deferred), None)
    # Initial scoping phase: the leading run of calls before any non-allowed tool
    initial_phase = []
    for n in names:
        if n in allowed:
            initial_phase.append(n)
        else:
            break
    if not initial_phase:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'initial tool call was {names[0]!r}, not a scoping tool', 'evidence_refs': [names[0]]}
    if first_deferred_idx is not None and (first_allowed_idx is None or first_deferred_idx < first_allowed_idx):
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'deferred tool {names[first_deferred_idx]!r} invoked before scoping tools', 'evidence_refs': names[:first_deferred_idx+1]}
    # Check that within the initial phase, only allowed tools used (already enforced by loop)
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'initial phase used only allowed scoping tools: {initial_phase}', 'evidence_refs': initial_phase}
