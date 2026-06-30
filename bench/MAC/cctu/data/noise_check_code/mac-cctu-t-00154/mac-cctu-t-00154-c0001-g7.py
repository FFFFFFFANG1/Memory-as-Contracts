def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    parts = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s.strip() for s in parts if s.strip()]
    if len(sentences) > 3:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'{len(sentences)} sentences exceeds 3', 'evidence_refs': []}
    closing = sentences[-1] if sentences else ''
    if re.search(r'\d', closing) or re.search(r'\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|hundred|thousand|million|billion)\b', closing, re.IGNORECASE):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'closing sentence contains numeric figure', 'evidence_refs': [closing]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'{len(sentences)} sentences and closing has no numbers', 'evidence_refs': []}
