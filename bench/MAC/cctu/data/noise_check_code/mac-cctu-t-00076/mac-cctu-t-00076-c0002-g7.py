def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no content lines', 'evidence_refs': []}
    bullet_re = re.compile(r'^\s*([-*+\u2022]|\d+[.)])\s+')
    bullet_lines = [ln for ln in lines if bullet_re.match(ln)]
    if len(bullet_lines) < 2 or len(bullet_lines) < max(1, len(lines) - 1):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'response not formatted as bulleted list', 'evidence_refs': lines[:3]}
    emphasis_patterns = [r'\*\*[^*\n]+\*\*', r'(?<!\*)\*(?!\*)[^*\n]+\*(?!\*)', r'__[^_\n]+__', r'(?<!_)_(?!_)[^_\n]+_(?!_)']
    for ln in bullet_lines:
        body = bullet_re.sub('', ln)
        for pat in emphasis_patterns:
            if re.search(pat, body):
                return {'observed_followed': False, 'confidence': 'high', 'reason': f'inline emphasis detected: {ln}', 'evidence_refs': [ln]}
    # one winner per line heuristic: no semicolons or ' and ' joining multiple names
    for ln in bullet_lines:
        body = bullet_re.sub('', ln).strip()
        if ';' in body:
            return {'observed_followed': False, 'confidence': 'medium', 'reason': f'multiple entries on one line: {ln}', 'evidence_refs': [ln]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'bulleted list with one entry per line and no inline emphasis', 'evidence_refs': bullet_lines[:3]}
