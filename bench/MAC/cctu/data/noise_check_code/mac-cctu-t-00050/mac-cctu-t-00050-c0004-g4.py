def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    lines = [l for l in text.splitlines() if l.strip()]
    if len(lines) < 2:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'need header + data row before prose', 'evidence_refs': []}
    header = lines[0].lower().replace(' ', '')
    expected = ['species','port','bait_store','fisherman_name']
    header_cols = [c.strip() for c in header.split(',')]
    if header_cols != expected:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'header columns are {header_cols}, expected {expected}', 'evidence_refs': [lines[0]]}
    data = lines[1]
    data_cols = [c.strip() for c in data.split(',')]
    if len(data_cols) < 4:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'data row does not have 4 CSV fields', 'evidence_refs': [data]}
    # Ensure header appears before any prose (header is line 0)
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'CSV schema header followed by CSV row present at top', 'evidence_refs': [lines[0], lines[1]]}
