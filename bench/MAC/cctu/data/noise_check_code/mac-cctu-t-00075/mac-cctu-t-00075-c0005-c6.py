def evaluate(trace):
    music_dance = {'choreographer_finder','local_band_finder','music_origin_identifier'}
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls present', 'evidence_refs': []}
    seen_fishing = False
    for i, c in enumerate(calls):
        name = c.get('name') or c.get('tool_name') or ''
        if name == 'fishing_activity_tracker':
            seen_fishing = True
            if i != 0 and not any((calls[j].get('name') or '') == 'fishing_activity_tracker' for j in range(i)):
                # first fishing call - check it came before any music/dance
                pass
        if name in music_dance and not seen_fishing:
            return {'observed_followed': False, 'confidence': 'high', 'reason': f'Music/dance tool {name} invoked at index {i} before any fishing_activity_tracker call', 'evidence_refs': [{'tool_index': i, 'name': name}]}
    first_name = (calls[0].get('name') or '')
    if first_name != 'fishing_activity_tracker':
        # Only a violation if music/dance tools were eventually used; otherwise constraint about anchoring before music/dance is vacuously fine
        used_md = any((c.get('name') or '') in music_dance for c in calls)
        if used_md:
            return {'observed_followed': False, 'confidence': 'high', 'reason': f'Tool sequence did not begin with fishing_activity_tracker (began with {first_name})', 'evidence_refs': [{'tool_index': 0, 'name': first_name}]}
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'No music/dance tools used; anchoring rule not clearly triggered', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'Sequence begins with fishing_activity_tracker before any music/dance retrieval tools', 'evidence_refs': [{'tool_index': 0, 'name': 'fishing_activity_tracker'}]}
