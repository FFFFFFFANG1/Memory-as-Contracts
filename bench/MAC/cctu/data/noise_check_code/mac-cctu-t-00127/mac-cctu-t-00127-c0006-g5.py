def evaluate(trace):
    import re
    text = (trace.get('final_response') or '')
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    bullet_re = re.compile(r'^(\*|-|\u2022|\d+[.)])\s+')
    bullets = [l for l in lines if bullet_re.match(l)]
    has_bullets = len(bullets) >= 2
    low = text.lower()
    mentions_cabin = any(k in low for k in ['cabin', 'capacity', 'passenger', 'seat'])
    mentions_range = 'range' in low or 'mileage' in low or 'distance' in low
    mentions_wingspan = 'wingspan' in low or 'wing span' in low
    # wingspan should not be emphasized; allow mention if cabin/range dominate
    cabin_range_count = sum(low.count(k) for k in ['cabin','range','capacity','passenger'])
    wingspan_count = low.count('wingspan') + low.count('wing span')
    emphasis_ok = cabin_range_count > wingspan_count
    followed = has_bullets and mentions_cabin and mentions_range and emphasis_ok
    reason = f'bullets={has_bullets} cabin={mentions_cabin} range={mentions_range} wingspan_mentions={wingspan_count} cabin_range_mentions={cabin_range_count}'
    return {'observed_followed': bool(followed), 'confidence': 'medium', 'reason': reason, 'evidence_refs': []}
