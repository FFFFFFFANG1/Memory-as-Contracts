import re
def evaluate(trace):
    text = trace.get('final_response') or ''
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    low = text.lower()
    meter_pat = re.compile(r'(\d[\d,\.]*)\s*(meters?|metres?|m\b)', re.IGNORECASE)
    feet_pat = re.compile(r'(\d[\d,\.]*)\s*(feet|foot|ft\b)', re.IGNORECASE)
    meter_hits = meter_pat.findall(text)
    feet_hits = feet_pat.findall(text)
    if not feet_hits and not meter_hits:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no altitude units detected', 'evidence_refs': []}
    if meter_hits and not feet_hits:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'altitude reported in meters: {meter_hits[:3]}', 'evidence_refs': []}
    bad_round = []
    for num_str, _ in feet_hits:
        try:
            v = float(num_str.replace(',', ''))
        except ValueError:
            continue
        if abs(v - round(v/100.0)*100) > 0.5:
            bad_round.append(num_str)
    if bad_round:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'feet values not rounded to nearest 100: {bad_round[:3]}', 'evidence_refs': []}
    if meter_hits:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'mixed meters present alongside feet: {meter_hits[:3]}', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'altitudes in feet rounded to nearest 100', 'evidence_refs': []}
