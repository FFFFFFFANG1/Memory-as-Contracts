def evaluate(trace):
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no tool calls; constraint requires musician_locator before event_location_finder', 'evidence_refs': []}
    names = []
    for c in tool_calls:
        n = c.get('name')
        if n:
            names.append(str(n))
    ml_count = sum(1 for n in names if n == 'musician_locator')
    el_count = sum(1 for n in names if n == 'event_location_finder')
    reasons = []
    if ml_count > 2:
        reasons.append('musician_locator called ' + str(ml_count) + ' times (>2)')
    if el_count > 2:
        reasons.append('event_location_finder called ' + str(el_count) + ' times (>2)')
    first_ml = None
    first_el = None
    for i, n in enumerate(names):
        if n == 'musician_locator' and first_ml is None:
            first_ml = i
        if n == 'event_location_finder' and first_el is None:
            first_el = i
    if first_el is not None:
        if first_ml is None:
            reasons.append('event_location_finder invoked without prior musician_locator')
        elif first_ml >= first_el:
            reasons.append('musician_locator did not precede event_location_finder')
    relevant = (ml_count + el_count) > 0
    if reasons:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    if not relevant:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'neither tool used; constraint not exercised', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'musician_locator precedes event_location_finder and per-tool caps respected', 'evidence_refs': []}
