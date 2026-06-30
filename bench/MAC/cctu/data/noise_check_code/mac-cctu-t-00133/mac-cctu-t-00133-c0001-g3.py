def evaluate(trace):
    import re
    text = (trace.get('final_response') or '')
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    low = text.lower()
    # Detect distance mentions
    mile_pat = re.compile(r'\b\d+(?:[\.,]\d+)?\s*(miles?|mi|mph)\b', re.I)
    meter_pat = re.compile(r'\b\d+(?:[\.,]\d+)?\s*(meters?|metres?|m)\b')
    foot_pat = re.compile(r'\b\d+(?:[\.,]\d+)?\s*(feet|ft|yards?|yd)\b', re.I)
    km_pat = re.compile(r'\b\d+(?:[\.,]\d+)?\s*(km|kilomet(er|re)s?)\b', re.I)
    miles_found = mile_pat.findall(text)
    meters_found = meter_pat.findall(text)
    feet_found = foot_pat.findall(text)
    km_found = km_pat.findall(text)
    bad = []
    if miles_found:
        bad.append(f'miles: {miles_found}')
    if feet_found:
        bad.append(f'feet/yd: {feet_found}')
    # 'm' alone is ambiguous - only flag if explicit meters/metres word
    explicit_meters = [m for m in meters_found if m.lower() in ('meter','meters','metre','metres')]
    if explicit_meters:
        bad.append(f'meters: {explicit_meters}')
    if bad:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Non-km distance units found: ' + '; '.join(bad), 'evidence_refs': []}
    if km_found:
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'Distances reported in km: {km_found}', 'evidence_refs': []}
    # No distances detected at all
    if re.search(r'distance|far|away|length', low):
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'Distance mentioned but no explicit units found', 'evidence_refs': []}
    return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No distance values found in final response', 'evidence_refs': []}
