def evaluate(trace):
    import re
    resp = trace.get('final_response')
    if resp is None:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final_response', 'evidence_refs': []}
    resp = str(resp)
    reasons = []
    # 1. length <= 10 chars
    if len(resp) > 10:
        reasons.append('exceeds 10 characters (len=' + str(len(resp)) + ')')
    # 2. no punctuation other than comma
    import string
    bad = [c for c in resp if c in string.punctuation and c != ',']
    if bad:
        reasons.append('disallowed punctuation: ' + ''.join(sorted(set(bad))))
    # 3. must contain 'Answer' immediately before a numerical result
    m = re.search(r'Answer\s*,?\s*-?\d+(?:\.\d+)?', resp)
    if not m:
        reasons.append("missing literal 'Answer' immediately before numerical result")
    # 4. interaction turns: count assistant steps in trajectory
    traj = trace.get('trajectory') or []
    turns = len(traj)
    if turns and not (5 <= turns <= 8):
        reasons.append('turns=' + str(turns) + ' not in [5,8]')
    elif not turns:
        reasons.append('no trajectory turns observable')
    # 5. tool calls 4-7
    tcs = trace.get('tool_calls') or []
    n = len(tcs)
    if not (4 <= n <= 7):
        reasons.append('tool_calls=' + str(n) + ' not in [4,7]')
    if reasons:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'all checks passed', 'evidence_refs': []}
