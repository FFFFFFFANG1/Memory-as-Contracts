def evaluate(trace):
    import re
    text = (trace.get('final_response') or '')
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    bullets = [l for l in lines if re.match(r'^([\-\*\+•]|\d+[\.\)])\s+', l)]
    p5 = {'china': ['china'], 'france': ['france'], 'russia': ['russia', 'soviet', 'ussr'], 'uk': ['united kingdom', 'uk', 'britain'], 'us': ['united states', 'usa', 'u.s.', 'us ']}
    found = {}
    for key, aliases in p5.items():
        for b in bullets:
            low = b.lower()
            if any(a in low for a in aliases):
                # find a number followed by parenthesized year
                m = re.search(r'(\d+)\s*\(([^)]*\b(1[89]\d{2}|20\d{2})\b[^)]*)\)', b)
                if m:
                    found[key] = b
                    break
    missing = [k for k in p5 if k not in found]
    if not missing:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'each P5 has bullet with count and year in parentheses', 'evidence_refs': list(found.values())}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'missing or malformed for: ' + ', '.join(missing), 'evidence_refs': bullets[:10]}
