def evaluate(trace):
    import re
    text = (trace.get('final_response') or '')
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    # find capacity mentions
    pattern = re.compile(r'(capacity[^.\n]{0,120}?)(\d{1,3}(?:[,\.]\d{3})+|\d{4,7})', re.IGNORECASE)
    matches = pattern.findall(text)
    if not matches:
        # also try 'seats' or 'seating'
        pattern2 = re.compile(r'(seat(?:s|ing)?[^.\n]{0,120}?)(\d{1,3}(?:[,\.]\d{3})+|\d{4,7})', re.IGNORECASE)
        matches = pattern2.findall(text)
    if not matches:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no stadium capacity mentioned', 'evidence_refs': []}
    season_pat = re.compile(r'(season|\b(19|20)\d{2}[\-/]\d{2,4}\b|\b(19|20)\d{2}\b)', re.IGNORECASE)
    bad = []
    for ctx, num in matches:
        raw = num.replace(',', '').replace('.', '')
        try:
            n = int(raw)
        except:
            continue
        rounded = n % 1000 == 0
        # find a small window around the match for season annotation
        idx = text.find(num)
        window = text[max(0, idx-160): idx+160]
        has_season = bool(season_pat.search(window))
        if not rounded or not has_season:
            bad.append({'value': n, 'rounded': rounded, 'season_annotated': has_season})
    if bad:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'capacity not rounded to thousand and/or missing season annotation', 'evidence_refs': bad}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'all capacities rounded to thousand with season annotation', 'evidence_refs': [m[1] for m in matches]}
