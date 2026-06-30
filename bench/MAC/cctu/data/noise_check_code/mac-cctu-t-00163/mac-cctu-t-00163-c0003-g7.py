def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls') or []
    final = trace.get('final_response') or ''
    altitude_tools = {'altitude_finder'}
    forbidden_for_altitude = ['historical_landmark_locator','water_body_info_retriever','historical_fact_finder']
    used_altitude_finder = any((tc.get('name') or '') == 'altitude_finder' for tc in tool_calls)
    # Heuristic: check if final response mentions altitude/elevation/meters
    mentions_altitude = bool(re.search(r'\b(altitude|elevation|meters|m\s+above|above sea level)\b', final, re.I))
    if not mentions_altitude and not used_altitude_finder:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No altitude content detected in trajectory or response.', 'evidence_refs': []}
    # Check other tools were not used to retrieve altitude-like info
    suspicious = []
    for tc in tool_calls:
        name = tc.get('name') or ''
        if name in altitude_tools:
            continue
        res = str(tc.get('result') or '')
        if re.search(r'\b(altitude|elevation)\b', res, re.I) or re.search(r'\d+\s*(m|meters|metres)\b', res, re.I):
            suspicious.append(name)
    # Check rounding to nearest ten in final response numbers near altitude mention
    rounded_ok = None
    if mentions_altitude:
        nums = re.findall(r'(\d{2,6})\s*(?:m\b|meters|metres)', final, re.I)
        if nums:
            vals = [int(n) for n in nums]
            rounded_ok = all(v % 10 == 0 for v in vals)
        else:
            rounded_ok = None
    followed = True
    reasons = []
    if suspicious:
        followed = False
        reasons.append(f'Altitude-like info from non-altitude_finder tools: {suspicious}')
    if mentions_altitude and not used_altitude_finder:
        followed = False
        reasons.append('Altitude mentioned in response but altitude_finder not used.')
    if rounded_ok is False:
        followed = False
        reasons.append('Reported meter values not rounded to nearest ten.')
    if followed and rounded_ok is None and mentions_altitude:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'Could not verify meter rounding from response.', 'evidence_refs': []}
    return {'observed_followed': followed, 'confidence': 'medium', 'reason': '; '.join(reasons) if reasons else 'Altitude lookups appear restricted to altitude_finder with meter values rounded to nearest ten.', 'evidence_refs': []}
