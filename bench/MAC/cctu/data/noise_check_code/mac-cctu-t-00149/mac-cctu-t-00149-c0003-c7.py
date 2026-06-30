def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    label_pat = re.compile(r'^(?:[-*\s]*)?(difference|subtraction|score\s*difference|delta|gap|diff)\s*[:=\-]\s*(-?\d+(?:\.\d+)?)', re.IGNORECASE)
    matched = None
    for l in lines:
        m = label_pat.match(l)
        if m:
            matched = (l, m.group(2))
            break
    if not matched:
        return {'observed_followed': False, 'confidence':'high','reason':'no labeled subtraction line found','evidence_refs':[]}
    # Try to verify numeric subtraction if two scores are visible
    nums = [float(x) for x in re.findall(r'-?\d+(?:\.\d+)?', text)]
    diff_val = float(matched[1])
    verified = False
    for i, a in enumerate(nums):
        for j, b in enumerate(nums):
            if i==j: continue
            if abs((a-b) - diff_val) < 1e-6 and a != diff_val and b != diff_val:
                verified = True
                break
        if verified: break
    if verified:
        return {'observed_followed': True, 'confidence':'high','reason':f'labeled line {matched[0]!r} matches subtraction of two values','evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'low','reason':f'labeled line {matched[0]!r} present but could not verify against two source scores','evidence_refs':[]}
