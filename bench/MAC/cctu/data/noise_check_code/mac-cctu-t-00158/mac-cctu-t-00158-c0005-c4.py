def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    bullets = [l for l in lines if re.match(r'^\s*([\-\*\u2022\u00b7]|\d+[.)])\s+', l)]
    if len(bullets) != 3:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'expected 3 bulleted lines, found {len(bullets)}', 'evidence_refs': []}
    joined = ' \n '.join(bullets).lower()
    needed = ['elevation', 'slope']
    bio_ok = any(k in joined for k in ['biodivers', 'flora', 'fauna', 'species', 'wildlife'])
    missing = [n for n in needed if n not in joined]
    if missing or not bio_ok:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'missing topics: {missing + ([] if bio_ok else ["biodiversity"])}', 'evidence_refs': []}
    if not bullets[-1].rstrip().endswith(';'):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'final bullet does not end with semicolon', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': '3 bullets with elevation, slope, biodiversity; ends with semicolon', 'evidence_refs': []}
