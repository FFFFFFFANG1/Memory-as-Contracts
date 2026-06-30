def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    # Single paragraph check: no blank line separators
    if re.search(r'\n\s*\n', text):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'response contains multiple paragraphs', 'evidence_refs': []}
    # Word count <= 200
    words = re.findall(r"\b[\w'-]+\b", text, flags=re.UNICODE)
    if len(words) > 200:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'exceeds 200 words ({len(words)})', 'evidence_refs': []}
    # French language heuristic via common stopwords/diacritics
    lower = text.lower()
    french_markers = [' le ', ' la ', ' les ', ' des ', ' du ', ' une ', ' un ', ' et ', ' est ', ' avec ', ' dans ', ' pour ', ' aux ', ' qui ', ' sont ', ' ces ', ' cette ']
    hits = sum(1 for m in french_markers if m in f' {lower} ')
    has_diacritics = bool(re.search(r'[àâäçéèêëîïôöùûüÿœæ]', lower))
    if hits < 3 and not has_diacritics:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'response does not appear to be in French', 'evidence_refs': []}
    # DOP-only dairy citation cannot be verified without external data
    return {'observed_followed': True, 'confidence': 'low', 'reason': 'single French paragraph within 200 words; DOP dairy verification not possible from trace', 'evidence_refs': []}
