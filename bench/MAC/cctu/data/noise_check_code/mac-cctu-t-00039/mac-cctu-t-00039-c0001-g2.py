def evaluate(trace):
    calls = trace.get('tool_calls') or []
    drt = [c for c in calls if c.get('name') == 'diplomatic_recognition_tracker']
    def_calls = [c for c in calls if c.get('name') == 'diplomatic_event_finder']
    final = trace.get('final_response') or ''
    if not calls and not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No trace data', 'evidence_refs': []}
    if len(drt) < 2:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'diplomatic_recognition_tracker invoked {len(drt)} times (<2)', 'evidence_refs': [{'type':'tool_calls','name':'diplomatic_recognition_tracker','count':len(drt)}]}
    if not def_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'diplomatic_event_finder never invoked for cross-reference', 'evidence_refs': [{'type':'tool_calls','name':'diplomatic_event_finder','count':0}]}
    # Check ordering: both recognition tracker calls and at least one event_finder call should occur before final response.
    # Since tool_calls list is pre-final by construction, just confirm presence.
    drt_indices = [c.get('index') for c in drt]
    def_indices = [c.get('index') for c in def_calls]
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'diplomatic_recognition_tracker called {len(drt)} times and diplomatic_event_finder called {len(def_calls)} times prior to final answer', 'evidence_refs': [{'type':'tool_calls','name':'diplomatic_recognition_tracker','indices':drt_indices},{'type':'tool_calls','name':'diplomatic_event_finder','indices':def_indices}]}
