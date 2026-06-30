def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    bullets = [l for l in lines if re.match(r'^\s*[-*+]\s+', l)]
    if len(bullets) < 2:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'fewer than 2 markdown bullets found', 'evidence_refs': bullets}
    last = bullets[-1]
    if 'historical_event_tool' not in last.lower():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'final bullet does not name historical_event_tool', 'evidence_refs': [last]}
    casualty_bullets = bullets[:-1]
    digit_bullets = [b for b in casualty_bullets if re.search(r'\d', b)]
    if not digit_bullets:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'no casualty figures (digits) found in non-final bullets', 'evidence_refs': casualty_bullets}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'bullets present with figures and final tool-name bullet', 'evidence_refs': bullets}
