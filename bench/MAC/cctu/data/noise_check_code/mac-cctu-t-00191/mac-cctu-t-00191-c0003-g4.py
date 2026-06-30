def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    # Find a 'Reforms' heading (markdown heading, bold, or line by itself)
    heading_pat = re.compile(r'(^|\n)\s*(#+\s*Reforms\b|\*\*Reforms\*\*|Reforms\s*:?)\s*(\n|$)', re.IGNORECASE)
    m = heading_pat.search(text)
    if not m:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No "Reforms" heading found', 'evidence_refs': []}
    after = text[m.end():]
    # Stop at next heading
    next_h = re.search(r'\n\s*(#+\s+\S|\*\*[^*]+\*\*\s*\n)', after)
    section = after[:next_h.start()] if next_h else after
    lines = [ln.rstrip() for ln in section.split('\n')]
    bullets = [ln for ln in lines if re.match(r'^\s*([-*+]|\d+\.)\s+', ln)]
    if not bullets:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No bulleted list under Reforms heading', 'evidence_refs': []}
    year_pat = re.compile(r'\b(1[0-9]{3}|20[0-9]{2})\b')
    with_year = [b for b in bullets if year_pat.search(b)]
    if len(with_year) < len(bullets):
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'{len(bullets)-len(with_year)} bullets missing a year', 'evidence_refs': bullets}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'Reforms heading with bulleted reforms and years', 'evidence_refs': bullets}
