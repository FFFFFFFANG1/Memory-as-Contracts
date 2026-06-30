def evaluate(trace):
    import re
    steps = trace.get('trajectory') or []
    msgs = []
    for s in steps:
        if not isinstance(s, dict):
            continue
        role = s.get('role')
        if role and role != 'assistant':
            continue
        c = s.get('content')
        if isinstance(c, str) and c.strip():
            msgs.append(c)
    final = trace.get('final_response')
    if isinstance(final, str) and final.strip() and final not in msgs:
        msgs.append(final)
    if not msgs:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no assistant messages found', 'evidence_refs': []}
    over = []
    for i, m in enumerate(msgs):
        w = len(re.findall(r"\S+", m))
        if w >= 120:
            over.append((i, w))
    if over:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'{len(over)} assistant message(s) >=120 words: {over}', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'all assistant messages under 120 words', 'evidence_refs': []}
