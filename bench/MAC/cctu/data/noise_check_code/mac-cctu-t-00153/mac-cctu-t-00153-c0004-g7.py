def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response to evaluate.', 'evidence_refs': []}
    usd_patterns = [r'\$\s*\d', r'\bUSD\b', r'\busd\b', r'\bdollars?\b\s*\d', r'\d+\s*(?:dollars?|USD)']
    ratio_patterns = [r'\b\d+\s*:\s*\d+\b', r'\b\d+(?:\.\d+)?\s*%', r'\b\d+(?:\.\d+)?\s*[xX]\b', r'\b\d+(?:\.\d+)?\s*times\b', r'\b\d+\s*/\s*\d+\b']
    hits = []
    for p in usd_patterns + ratio_patterns:
        m = re.search(p, text)
        if m:
            hits.append(m.group(0))
    if hits:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Found numeric ratio/USD evidence: {hits[:5]}', 'evidence_refs': []}
    if re.search(r'\$\d|\d+\s*:\s*\d', text):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Numeric monetary or ratio symbol present.', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'No USD amounts or numeric ratios detected in final response.', 'evidence_refs': []}
