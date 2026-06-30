def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    bullet_re = re.compile(r'^\s*([-*+\u2022]|\d+[.)])\s+')
    bullets = [l for l in lines if bullet_re.match(l)]
    if len(bullets) < 2:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'no bullet list detected', 'evidence_refs': []}
    # Check single contiguous list
    idxs = [i for i,l in enumerate(lines) if bullet_re.match(l)]
    contiguous = idxs == list(range(idxs[0], idxs[0]+len(idxs)))
    if not contiguous:
        return {'observed_followed': False, 'confidence': 'low', 'reason': 'bullets not in single contiguous list', 'evidence_refs': []}
    last = bullets[-1].lower()
    has_total = any(k in last for k in ['grand total','total:','total '])
    if not has_total:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'no grand total at bottom of list', 'evidence_refs': []}
    # Try to detect dates and verify ordering on non-total bullets
    date_patterns = [
        (re.compile(r'(\d{4})-(\d{1,2})-(\d{1,2})'), 'ymd'),
        (re.compile(r'(\d{1,2})/(\d{1,2})/(\d{4})'), 'mdy'),
        (re.compile(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2}),?\s*(\d{4})?', re.I), 'mon'),
    ]
    months = {m:i+1 for i,m in enumerate(['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'])}
    def parse(l):
        for p, kind in date_patterns:
            m = p.search(l)
            if m:
                if kind=='ymd': return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
                if kind=='mdy': return (int(m.group(3)), int(m.group(1)), int(m.group(2)))
                if kind=='mon':
                    yr = int(m.group(3)) if m.group(3) else 0
                    return (yr, months[m.group(1)[:3].lower()], int(m.group(2)))
        return None
    items = bullets[:-1]
    dates = [parse(l) for l in items]
    if any(d is None for d in dates):
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'could not parse all itinerary dates', 'evidence_refs': []}
    ordered = all(dates[i] <= dates[i+1] for i in range(len(dates)-1))
    if not ordered:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'bullets not ordered by travel date', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'single bullet list ordered by date with grand total last', 'evidence_refs': []}
