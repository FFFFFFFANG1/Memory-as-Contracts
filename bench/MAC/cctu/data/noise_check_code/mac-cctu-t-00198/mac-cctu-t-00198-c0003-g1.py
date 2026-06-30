def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'No final response', 'evidence_refs':[]}
    # find area-like mentions
    area_pattern = re.compile(r'(\d+\.\d+)\s*(?:km\^?2|km²|square\s*kilomet(?:er|re)s?)', re.IGNORECASE)
    matches = area_pattern.findall(text)
    # also check for any park area mention at all
    mentions_area = bool(re.search(r'park\s*area|area\s*of\s*the\s*park|area[:=]', text, re.IGNORECASE)) or bool(matches)
    if not mentions_area:
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'No park area output found in final response', 'evidence_refs':[]}
    if not matches:
        return {'observed_followed': False, 'confidence':'medium', 'reason':'Park area mentioned but not in square kilometers with decimal value', 'evidence_refs':[text[:200]]}
    # check 2 decimal places
    bad_precision = [m for m in matches if len(m.split('.')[-1]) != 2]
    if bad_precision:
        return {'observed_followed': False, 'confidence':'high', 'reason': f'Area not rounded to 2 decimals: {bad_precision}', 'evidence_refs': matches}
    # check inline citation of coral or seagrass habitat
    has_citation = bool(re.search(r'coral|seagrass', text, re.IGNORECASE))
    if not has_citation:
        return {'observed_followed': False, 'confidence':'high', 'reason':'No coral/seagrass habitat citation found inline', 'evidence_refs': matches}
    return {'observed_followed': True, 'confidence':'medium', 'reason':'Area reported in km² with 2 decimals and habitat cited', 'evidence_refs': matches}
