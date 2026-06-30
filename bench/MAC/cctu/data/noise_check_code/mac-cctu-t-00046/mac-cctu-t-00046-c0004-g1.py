def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    tool_count = len(tool_calls)
    if not response.strip() and not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    if tool_count > 3:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'tool calls {tool_count} > 3', 'evidence_refs': []}
    lines = [ln.rstrip() for ln in response.splitlines() if ln.strip()]
    if not lines:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'empty response', 'evidence_refs': []}
    bullet_re = re.compile(r'^\s*([\-\*\+\u2022]|\d+[\.\)])\s+(.+)$')
    bullet_items = []
    non_bullet_lines = []
    for ln in lines:
        m = bullet_re.match(ln)
        if m:
            bullet_items.append(m.group(2).strip())
        else:
            non_bullet_lines.append(ln)
    if len(bullet_items) < 2:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'response is not a bulleted list of entities', 'evidence_refs': []}
    if len(non_bullet_lines) > 0:
        joined = ' '.join(non_bullet_lines).strip()
        if len(joined) > 0 and not re.match(r'^[A-Z].{0,80}:$', joined):
            return {'observed_followed': False, 'confidence': 'medium', 'reason': 'non-bullet content present alongside list', 'evidence_refs': []}
    trailing = re.compile(r'[\.,;:!\?]$')
    bad = [it for it in bullet_items if trailing.search(it)]
    if bad:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'bullet items have trailing punctuation: {bad[:3]}', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'{len(bullet_items)} bulleted entities, no trailing punctuation, {tool_count} tool calls', 'evidence_refs': []}
