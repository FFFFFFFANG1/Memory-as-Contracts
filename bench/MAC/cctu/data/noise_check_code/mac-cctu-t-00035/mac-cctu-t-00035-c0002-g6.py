def evaluate(trace):
    import re
    final = (trace.get('final_response') or '')
    text = final.lower()
    # Find casualty report sections
    if 'casualt' not in text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No casualty report detected', 'evidence_refs': []}
    # Look for fire-safety recommendation language
    has_fire = bool(re.search(r'fire[- ]safety|fire safety reform|urban fire', text))
    has_recommend = 'recommend' in text
    if not (has_fire and has_recommend):
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Missing fire-safety reform recommendation', 'evidence_refs': []}
    # Try to verify two-sentence structure near each casualty mention
    # Split into blocks by casualty occurrences
    segments = re.split(r'(?i)casualt[^\n]*', final)
    # crude: check that a recommendation block of ~2 sentences exists
    rec_matches = re.findall(r'(?i)(recommend[^\n]*?(?:\.[^\n]*?\.)|recommendation[^\n]*?(?:\.[^\n]*?\.))', final)
    if not rec_matches:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'Could not parse recommendation sentences', 'evidence_refs': []}
    # Check each recommendation is two sentences and mentions fire safety
    ok = 0
    for m in rec_matches:
        sents = re.findall(r'[^.!?]+[.!?]', m)
        if len(sents) >= 2 and re.search(r'(?i)fire[- ]safety|urban fire', m):
            ok += 1
    if ok >= 1:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': f'Found {ok} two-sentence fire-safety recommendation(s)', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'low', 'reason': 'Recommendation not two sentences or off-topic', 'evidence_refs': []}
