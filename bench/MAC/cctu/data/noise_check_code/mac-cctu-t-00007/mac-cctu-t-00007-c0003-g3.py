def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    steps = []
    for s in traj:
        tcs = s.get('tool_calls') or []
        if tcs:
            steps.append((s.get('content') or '', tcs))
    if not steps:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool-calling steps','evidence_refs':[]}
    bad = []
    for idx,(content, tcs) in enumerate(steps):
        text = content.strip()
        sentences = [x for x in re.split(r'(?<=[.!?])\s+', text) if x.strip()]
        names = [tc.get('name') or (tc.get('function') or {}).get('name','') for tc in tcs]
        # need at least one sentence per tool mentioning it or providing a rationale
        if not text or len(sentences) < len(tcs):
            bad.append({'step':idx,'tools':names,'sentences':len(sentences),'needed':len(tcs)})
            continue
        # check each tool name appears or rationale keywords present
        low = text.lower()
        for n in names:
            tok = n.lower().split('_')[0] if n else ''
            if tok and tok not in low and not re.search(r'because|to (find|get|retrieve|check|query|locate|answer)|in order to|so that|will use|use .* to', low):
                bad.append({'step':idx,'tool':n,'reason':'no rationale tying to objective'})
                break
    if bad:
        return {'observed_followed': False, 'confidence':'low','reason':'missing one-sentence rationale for some tool selections','evidence_refs':bad[:5]}
    return {'observed_followed': True, 'confidence':'low','reason':'each tool-calling step contains sentence-level rationale referencing tool/objective','evidence_refs':[]}
