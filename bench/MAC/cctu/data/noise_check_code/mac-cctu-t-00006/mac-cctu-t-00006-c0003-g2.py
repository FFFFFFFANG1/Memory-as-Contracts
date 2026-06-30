def evaluate(trace):
    import re
    final = (trace.get('final_response') or '')
    text = final.lower()
    pattern = re.compile(r'no[- ]confidence|motion of no[- ]confidence|vote of no[- ]confidence')
    mentions = pattern.findall(text)
    calls = trace.get('tool_calls') or []
    pes = [c for c in calls if (c.get('name') or '') == 'political_event_search']
    if not mentions:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'No motion-of-no-confidence claims detected in final response.', 'evidence_refs': []}
    if len(pes) < 2:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Found no-confidence claims but only {len(pes)} political_event_search call(s); need >=2 independent results.', 'evidence_refs': [{'type':'tool_calls','count':len(pes)}]}
    # Check independence: distinct arguments
    seen = set()
    for c in pes:
        args = c.get('arguments')
        try:
            key = repr(sorted(args.items())) if isinstance(args, dict) else repr(args)
        except Exception:
            key = repr(args)
        seen.add(key)
    if len(seen) < 2:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Multiple political_event_search calls were not independent (identical arguments).', 'evidence_refs': [{'type':'distinct_arg_sets','count':len(seen)}]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'No-confidence claims present and {len(pes)} political_event_search calls with {len(seen)} distinct argument sets found.', 'evidence_refs': [{'type':'tool_calls','count':len(pes)}]}
