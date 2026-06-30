def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    if not text.endswith('.'):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'does not end with a period', 'evidence_refs': []}
    # extract last sentence
    parts = re.split(r'(?<=[.!?])\s+', text)
    last = parts[-1].strip() if parts else text
    # ensure single sentence terminated by exactly one period
    if last.count('.') != 1 or last.endswith('..'):
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'last sentence not a single period-terminated sentence', 'evidence_refs': [last]}
    low = last.lower()
    keywords = ['larger', 'greater', 'higher', 'taller', 'bigger', 'more', 'exceeds', 'surpass']
    if not any(k in low for k in keywords):
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'final sentence does not summarize which quantity is larger', 'evidence_refs': [last]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'final sentence summarizes larger quantity and ends with period', 'evidence_refs': [last]}
