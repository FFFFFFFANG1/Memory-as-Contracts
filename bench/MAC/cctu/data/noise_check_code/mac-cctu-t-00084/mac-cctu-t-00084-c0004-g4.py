def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no tool calls; constraint requires parallel beach_characteristic_finder and nearby_business_locator invocations', 'evidence_refs': []}
    from collections import defaultdict
    groups = defaultdict(list)
    for c in calls:
        key = c.get('iteration')
        if key is None:
            key = c.get('index')
        groups[key].append(str(c.get('name') or ''))
    beach = 'beach_characteristic_finder'
    nearby = 'nearby_business_locator'
    hist = 'historical_location_finder'
    pair_issues = []
    saw_pair = False
    for k, names in groups.items():
        has_b = beach in names
        has_n = nearby in names
        if has_b and has_n:
            saw_pair = True
        elif has_b or has_n:
            pair_issues.append('iteration ' + str(k) + ' missing parallel pair')
    hist_issues = []
    for k, names in groups.items():
        cnt = names.count(hist)
        if cnt > 3:
            hist_issues.append('iteration ' + str(k) + ' called historical_location_finder ' + str(cnt) + ' times')
    any_beach_or_nearby = any(beach in n or nearby in n for n in groups.values())
    any_hist = any(hist in n for n in groups.values())
    if not any_beach_or_nearby and not any_hist:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'no relevant tool calls observed to assess parallel pairing or historical_location_finder usage', 'evidence_refs': []}
    reasons = []
    if pair_issues:
        reasons.append('; '.join(pair_issues[:5]))
    if hist_issues:
        reasons.append('; '.join(hist_issues[:5]))
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    if saw_pair or not any_beach_or_nearby:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'parallel pairing satisfied and historical_location_finder within limit', 'evidence_refs': []}
    return {'observed_followed': None, 'confidence': 'low', 'reason': 'insufficient evidence to confirm parallel invocation', 'evidence_refs': []}
