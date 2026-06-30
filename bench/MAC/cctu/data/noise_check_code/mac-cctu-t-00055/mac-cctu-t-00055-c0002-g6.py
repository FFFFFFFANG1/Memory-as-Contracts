def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response', 'evidence_refs': []}
    words = re.findall(r"\b[\w'\-]+\b", text, flags=re.UNICODE)
    wc = len(words)
    if wc > 200:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Word count {wc} exceeds 200', 'evidence_refs': [f'word_count={wc}']}
    french_markers = [' le ', ' la ', ' les ', ' des ', ' du ', ' une ', ' un ', ' et ', ' est ', ' sont ', ' avec ', ' pour ', ' dans ', ' aux ', ' aux ', ' qui ', ' que ', ' sur ', ' par ', "d'", "l'", "qu'", 'ç', 'é', 'è', 'ê', 'à', 'ô']
    low = ' ' + text.lower() + ' '
    hits = sum(1 for m in french_markers if m in low)
    if hits < 3:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Final response does not appear to be in French (markers={hits})', 'evidence_refs': [text[:120]]}
    # Check for non-Romanized scripts in place-name-like tokens
    non_roman = re.search(r'[\u0400-\u04FF\u0600-\u06FF\u0900-\u097F\u4E00-\u9FFF\u3040-\u30FF\uAC00-\uD7AF]', text)
    if non_roman:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Non-Romanized script detected in final response', 'evidence_refs': [non_roman.group(0)]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'French markers={hits}, word_count={wc}, no non-Romanized scripts', 'evidence_refs': [f'word_count={wc}', f'french_markers={hits}']}
