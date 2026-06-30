def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found.', 'evidence_refs': []}
    allowed_triage = {'philosopher_topic_finder', 'historical_invention_info'}
    spatial = {'elevation_retriever','mountain_peak_altitude_finder','nearby_reserve_locator','park_feature_locator','protected_area_info_retriever','historical_experiment_locator'}
    # Determine triage phase: leading contiguous calls that are in allowed_triage.
    # Violation: a spatial tool appears before any allowed_triage call, OR appears in same first iteration as triage allowed tools.
    first_iter = calls[0].get('iteration')
    triage_calls = [c for c in calls if c.get('iteration') == first_iter]
    names_in_first = [c.get('name') for c in triage_calls]
    # If the very first tool used is spatial, that's a clear violation of deferring spatial lookups.
    if names_in_first and names_in_first[0] in spatial:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'First tool call {names_in_first[0]} is a spatial lookup; spatial lookups should be deferred past triage.', 'evidence_refs': [{'index': calls[0].get('index'), 'name': names_in_first[0]}]}
    # If any allowed triage tool was used, check that no spatial tool was used before the last triage-tool call.
    triage_indices = [i for i,c in enumerate(calls) if c.get('name') in allowed_triage]
    spatial_indices = [i for i,c in enumerate(calls) if c.get('name') in spatial]
    if triage_indices:
        last_triage = max(triage_indices)
        early_spatial = [i for i in spatial_indices if i < last_triage]
        # Also any spatial call interleaved before completing triage is a violation
        first_spatial = min(spatial_indices) if spatial_indices else None
        first_triage = min(triage_indices)
        if first_spatial is not None and first_spatial < first_triage:
            return {'observed_followed': False, 'confidence': 'high', 'reason': 'Spatial tool used before triage tools.', 'evidence_refs': [{'index': calls[first_spatial].get('index'), 'name': calls[first_spatial].get('name')}]}
        if early_spatial:
            return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Spatial tool used during triage phase (interleaved with allowed triage tools).', 'evidence_refs': [{'index': calls[i].get('index'), 'name': calls[i].get('name')} for i in early_spatial]}
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Triage phase used only allowed tools; spatial lookups deferred.', 'evidence_refs': [{'index': calls[i].get('index'), 'name': calls[i].get('name')} for i in triage_indices]}
    # No allowed triage tool was ever used; cannot confirm a triage phase happened.
    return {'observed_followed': None, 'confidence': 'low', 'reason': 'No philosopher_topic_finder or historical_invention_info calls observed; triage phase indeterminate.', 'evidence_refs': []}
