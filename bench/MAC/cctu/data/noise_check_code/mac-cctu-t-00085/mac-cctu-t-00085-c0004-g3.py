def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    trajectory = trace.get('trajectory') or []
    if not response.strip() and not tool_calls and not trajectory:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no observable behavior', 'evidence_refs': []}
    reasons = []
    stripped = response.strip()
    # Length check: <=10 characters
    if len(stripped) > 10:
        reasons.append('response exceeds 10 characters (len=' + str(len(stripped)) + ')')
    # Punctuation check: no punctuation except comma
    import string
    allowed_punct = {','}
    bad_punct = [c for c in stripped if c in string.punctuation and c not in allowed_punct]
    if bad_punct:
        reasons.append('disallowed punctuation: ' + ''.join(sorted(set(bad_punct))))
    # Must include 'Answer' immediately before numerical result
    m = re.search(r'Answer\s*,?\s*(-?\d+(?:\.\d+)?)', stripped)
    if not m:
        reasons.append("missing 'Answer' identifier immediately before numerical result")
    # Turns: 5-8 interaction turns
    n_turns = len(trajectory)
    if n_turns and not (5 <= n_turns <= 8):
        reasons.append('turns out of range 5-8: ' + str(n_turns))
    # Tool calls: 4-7
    n_tools = len(tool_calls)
    if not (4 <= n_tools <= 7):
        reasons.append('tool calls out of range 4-7: ' + str(n_tools))
    if reasons:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'all constraint parts satisfied', 'evidence_refs': []}
