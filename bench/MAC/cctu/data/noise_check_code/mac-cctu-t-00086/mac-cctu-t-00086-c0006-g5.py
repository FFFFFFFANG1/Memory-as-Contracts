def evaluate(trace):
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'constraint requires tool usage but no tool calls were made', 'evidence_refs': []}
    names = [str(c.get('name') or '') for c in tool_calls]
    if 'astronomical_discovery_finder' in names:
        idxs = [i for i, n in enumerate(names) if n == 'astronomical_discovery_finder']
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'forbidden tool astronomical_discovery_finder was invoked', 'evidence_refs': [{'tool_call_indices': idxs}]}
    chl_calls = [c for c in tool_calls if str(c.get('name') or '') == 'concert_hall_locator']
    total_chl = len(chl_calls)
    if total_chl == 0:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'concert_hall_locator was never invoked', 'evidence_refs': []}
    # Try to group by venue argument to verify >=2 per venue
    from collections import Counter
    venue_keys = ['venue', 'venue_name', 'hall', 'hall_name', 'concert_hall', 'name', 'location']
    venue_counts = Counter()
    unknown_venue = 0
    for c in chl_calls:
        args = c.get('arguments') or {}
        if not isinstance(args, dict):
            unknown_venue += 1
            continue
        key_found = None
        for k in venue_keys:
            if k in args and args[k]:
                key_found = str(args[k]).strip().lower()
                break
        if key_found:
            venue_counts[key_found] += 1
        else:
            unknown_venue += 1
    if venue_counts:
        deficient = [v for v, n in venue_counts.items() if n < 2]
        if deficient:
            return {'observed_followed': False, 'confidence': 'medium', 'reason': 'concert_hall_locator invoked fewer than 2 times for venue(s): ' + ', '.join(deficient[:5]), 'evidence_refs': [{'venue_counts': dict(venue_counts)}]}
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'concert_hall_locator invoked at least twice per identified venue and forbidden tool not used', 'evidence_refs': [{'venue_counts': dict(venue_counts)}]}
    # Fallback: no venue arg parseable; require at least 2 total calls as minimal proxy
    if total_chl < 2:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'concert_hall_locator invoked only ' + str(total_chl) + ' time(s); need at least 2 per venue', 'evidence_refs': []}
    return {'observed_followed': None, 'confidence': 'low', 'reason': 'concert_hall_locator invoked ' + str(total_chl) + ' times but venue arguments not identifiable to verify per-venue minimum', 'evidence_refs': []}
