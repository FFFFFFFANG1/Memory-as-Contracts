def evaluate(trace):
    import re
    text = (trace.get('final_response') or '')
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    lines = text.splitlines()
    bullets = [l for l in lines if re.match(r'^\s*[-*+]\s+', l) or re.match(r'^\s*\d+\.\s+', l)]
    if len(bullets) < 2:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'only {len(bullets)} bullet(s) found; severity tiers not enumerated', 'evidence_refs': ['final_response']}
    # ICAO-coded labels: look for short uppercase codes or parenthesized codes in bullets
    icao_like = 0
    for b in bullets:
        if re.search(r'\b[A-Z]{2,5}\b', b) or re.search(r'\([A-Z0-9/-]{1,6}\)', b):
            icao_like += 1
    if icao_like < max(2, len(bullets)//2):
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'bullets lack ICAO-coded labels ({icao_like}/{len(bullets)})', 'evidence_refs': ['final_response']}
    # Narrative = non-bullet, non-empty lines
    narrative_lines = [l for l in lines if l.strip() and not (re.match(r'^\s*[-*+]\s+', l) or re.match(r'^\s*\d+\.\s+', l) or re.match(r'^\s*#', l))]
    narrative = ' '.join(narrative_lines).strip()
    sentences = [s for s in re.split(r'(?<=[.!?])\s+', narrative) if s.strip()]
    if len(sentences) > 3:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'narrative has {len(sentences)} sentences (>3)', 'evidence_refs': ['final_response']}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'{len(bullets)} bullets with ICAO-like codes; narrative {len(sentences)} sentence(s)', 'evidence_refs': ['final_response']}
