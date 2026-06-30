def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').rstrip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    lines = text.split('\n')
    # find trailing contiguous bullet block
    bullet_re = re.compile(r'^\s*([\-\*\u2022]|\d+\.)\s+.+')
    i = len(lines) - 1
    bullets = []
    while i >= 0 and bullet_re.match(lines[i]):
        bullets.append(lines[i])
        i -= 1
    bullets.reverse()
    if len(bullets) < 1:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no trailing bulleted summary found', 'evidence_refs': []}
    # check elevation-like content (numbers with units or 'elevation')
    num_re = re.compile(r'\d')
    if not any(num_re.search(b) for b in bullets):
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'bullets lack numeric elevation values', 'evidence_refs': bullets}
    # check final bullet has no trailing punctuation
    final = bullets[-1].rstrip()
    if final and final[-1] in '.,;:!?':
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'final bullet ends with punctuation: ' + final[-1], 'evidence_refs': [final]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'trailing bulleted summary present with no trailing punctuation on final bullet', 'evidence_refs': bullets}
