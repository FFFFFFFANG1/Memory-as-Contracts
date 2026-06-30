def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    low = text.lower()
    mw_patterns = [r'moment magnitude', r'\bm_?w\b', r'\bmw\s*[0-9]', r'mww', r'\(mw\)']
    has_mw = any(re.search(p, low) for p in mw_patterns)
    coord_pair = re.search(r'\(\s*-?\d{1,3}(?:\.\d+)?\s*[°]?\s*[NS]?\s*,\s*-?\d{1,3}(?:\.\d+)?\s*[°]?\s*[EW]?\s*\)', text)
    has_magnitude_mention = bool(re.search(r'magnitud', low))
    if not has_magnitude_mention and not coord_pair:
        return {'observed_followed': None,'confidence':'unknown','reason':'no earthquake magnitude/coordinate content found','evidence_refs':[]}
    followed = bool(has_mw and coord_pair)
    return {'observed_followed': followed, 'confidence':'medium' if followed else 'medium', 'reason': f'has_mw={has_mw}, coord_pair={bool(coord_pair)}', 'evidence_refs':[]}
