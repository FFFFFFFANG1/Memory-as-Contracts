def evaluate(trace):
    import re
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls to assess', 'evidence_refs': []}
    names = [ (c.get('name') or '') for c in calls ]
    text = ' '.join([str(trace.get('final_response') or '')] + [str(c.get('arguments') or '') for c in calls]).lower()
    ref_keywords = ['university','college','institution','school','country','nation','catalog','course','curriculum','department','faculty']
    looks_referencey = any(k in text for k in ref_keywords)
    other_lookup_tools = {'library_collection_locator','historical_civilization_identifier','event_location_finder'}
    used_ccq = 'course_catalog_query' in names
    used_other_first = False
    for n in names:
        if n == 'course_catalog_query':
            break
        if n in other_lookup_tools:
            used_other_first = True
            break
    if not looks_referencey and not used_ccq:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'no clear institutional/country reference lookup detected', 'evidence_refs': []}
    if used_other_first and not used_ccq:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'used another lookup tool before course_catalog_query for reference data', 'evidence_refs': names}
    if used_ccq:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'course_catalog_query used as primary lookup', 'evidence_refs': names}
    return {'observed_followed': None, 'confidence': 'low', 'reason': 'insufficient signal', 'evidence_refs': names}
