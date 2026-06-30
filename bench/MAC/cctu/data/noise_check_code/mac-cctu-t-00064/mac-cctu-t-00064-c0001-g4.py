def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls') or []
    final = trace.get('final_response') or ''
    if not tool_calls and not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no trace data', 'evidence_refs': []}
    names = [tc.get('name','') for tc in tool_calls]
    laf_count = sum(1 for n in names if n == 'literary_author_finder')
    other_count = len(names) - laf_count
    primary_ok = laf_count > 0 and laf_count >= other_count
    lines = final.splitlines()
    bullet_lines = [l.strip() for l in lines if re.match(r'^\s*[-*•]\s+', l)]
    pair_pattern = re.compile(r'[A-Za-z].*[-:–—,].*[A-Za-z]')
    pair_bullets = [b for b in bullet_lines if pair_pattern.search(b)]
    has_bullets = len(pair_bullets) >= 1
    bullet_pos = -1
    for i,l in enumerate(lines):
        if re.match(r'^\s*[-*•]\s+', l) and pair_pattern.search(l):
            bullet_pos = i; break
    final_marker = None
    for i,l in enumerate(lines):
        if re.search(r'(final answer|final:|answer:|conclusion)', l, re.I):
            final_marker = i; break
    order_ok = True if final_marker is None else (bullet_pos != -1 and bullet_pos < final_marker)
    followed = primary_ok and has_bullets and order_ok
    return {'observed_followed': bool(followed), 'confidence': 'medium', 'reason': f'laf_calls={laf_count} other_calls={other_count} pair_bullets={len(pair_bullets)} order_ok={order_ok}', 'evidence_refs': []}
