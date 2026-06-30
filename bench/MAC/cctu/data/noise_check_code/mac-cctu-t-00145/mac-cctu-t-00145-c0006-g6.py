def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    parts = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
    if len(parts) > 3:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'{len(parts)} sentences exceeds 3', 'evidence_refs': [text]}
    first = parts[0].lower()
    has_number = bool(re.search(r'\b(\d+|zero|one|two|three|four|five|six|seven|eight|nine|ten)\b', first))
    mentions_new = ('new' in first or 'ingest' in first or 'added' in first)
    if has_number and mentions_new:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'first sentence leads with count of new items; <=3 sentences', 'evidence_refs': [parts[0]]}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'first sentence missing count or new-item reference', 'evidence_refs': [parts[0]]}
