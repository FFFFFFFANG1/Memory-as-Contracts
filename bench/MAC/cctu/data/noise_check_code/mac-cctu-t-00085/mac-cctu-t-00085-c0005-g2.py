def evaluate(trace):
    import re
    resp = str(trace.get('final_response') or '')
    if not resp.strip():
        return {'observed_followed': False, 'confidence':'high','reason':'empty response','evidence_refs':[]}
    reasons = []
    stripped = resp.strip()
    if len(stripped) > 10:
        reasons.append(f'length {len(stripped)} exceeds 10 chars')
    # punctuation: allow letters, digits, whitespace, comma
    bad = [c for c in stripped if not (c.isalnum() or c.isspace() or c == ',')]
    if bad:
        reasons.append(f'disallowed punctuation: {sorted(set(bad))}')
    # must include 'Answer' immediately before a numerical result
    m = re.search(r'Answer\s*[:=]?\s*(-?\d+(?:\.\d+)?)', stripped)
    if not m:
        reasons.append('missing identifier Answer immediately before numerical result')
    traj = trace.get('trajectory') or []
    turns = len(traj)
    if turns and not (5 <= turns <= 8):
        reasons.append(f'interaction turns {turns} not in [5,8]')
    tcs = trace.get('tool_calls') or []
    n = len(tcs)
    if not (4 <= n <= 7):
        reasons.append(f'tool calls {n} not in [4,7]')
    if reasons:
        return {'observed_followed': False, 'confidence':'high','reason':'; '.join(reasons),'evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'high','reason':'all checks passed','evidence_refs':[]}
