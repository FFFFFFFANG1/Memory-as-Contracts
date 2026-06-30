def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    parts = re.split(r'(?<=[.!?])\s+', text)
    sentences = [p.strip() for p in parts if p.strip()]
    if not sentences:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no sentences detected', 'evidence_refs': []}
    if len(sentences) > 3:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'found {len(sentences)} sentences (>3)', 'evidence_refs': sentences}
    closing = sentences[-1]
    digit_match = re.search(r'\d', closing)
    word_nums = re.search(r'\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|billion)\b', closing, re.IGNORECASE)
    if digit_match:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'closing sentence contains digit: {closing}', 'evidence_refs': [closing]}
    if word_nums:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'closing sentence contains numeric word: {word_nums.group(0)}', 'evidence_refs': [closing]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'{len(sentences)} sentences, closing has no numeric figure', 'evidence_refs': [closing]}
