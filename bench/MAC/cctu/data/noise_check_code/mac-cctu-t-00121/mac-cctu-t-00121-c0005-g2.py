def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response', 'evidence_refs': []}
    # Check single paragraph (no blank-line separated paragraphs)
    paragraphs = [p for p in re.split(r'\n\s*\n', text) if p.strip()]
    single_para = len(paragraphs) == 1
    words = re.findall(r"\b[\w'-]+\b", text)
    wc = len(words)
    # Allow ~10% tolerance around 200
    length_ok = 180 <= wc <= 220
    # Find years to test chronological order
    years = [int(y) for y in re.findall(r'\b(1[0-9]{3}|20[0-9]{2})\b', text)]
    chron_ok = None
    if len(years) >= 2:
        chron_ok = all(years[i] <= years[i+1] for i in range(len(years)-1))
    reasons = []
    reasons.append(f'word_count={wc} (target 200)')
    reasons.append(f'paragraphs={len(paragraphs)}')
    reasons.append(f'years_in_text={years}')
    if not single_para or not length_ok:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    if chron_ok is False:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Years not in chronological order: ' + '; '.join(reasons), 'evidence_refs': []}
    if chron_ok is None:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'Length/paragraph OK but chronological order unverifiable: ' + '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
