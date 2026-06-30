def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    date_pat = re.compile(r'\b(?:\d{1,2}\s+)?(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}?,?\s*\d{4}\b|\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b', re.IGNORECASE)
    dates = date_pat.findall(text)
    erupt = re.search(r'erupt', text, re.IGNORECASE)
    evac = re.search(r'evacuat', text, re.IGNORECASE)
    sentences = re.split(r'(?<=[.!?])\s+', text)
    sentence_hit = False
    for s in sentences:
        if re.search(r'erupt', s, re.IGNORECASE) and re.search(r'evacuat', s, re.IGNORECASE) and len(date_pat.findall(s)) >= 2:
            sentence_hit = True
            break
    if sentence_hit:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'sentence cites both eruption and evacuation order dates', 'evidence_refs': []}
    if erupt and evac and len(dates) >= 2:
        return {'observed_followed': True, 'confidence': 'low', 'reason': 'mentions eruption, evacuation, and >=2 dates but not in single sentence', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'missing eruption date, evacuation date, or natural-language sentence form', 'evidence_refs': []}
