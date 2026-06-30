def evaluate(trace):
    import re
    resp = trace.get('final_response') or ''
    if not resp.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    has_pipe_table = bool(re.search(r'^\s*\|.*\|\s*$', resp, re.MULTILINE))
    has_separator = bool(re.search(r'^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$', resp, re.MULTILINE))
    has_table = has_pipe_table and has_separator
    # count assistant turns/tool iterations as proxy for interaction turns
    traj = trace.get('trajectory') or []
    turns = len(traj) if traj else 0
    too_many = turns > 6
    if has_table:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'response contains a markdown table', 'evidence_refs': ['final_response']}
    if too_many:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'used {turns} turns exceeding 6', 'evidence_refs': ['trajectory']}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'narrative without tables and within 6 turns', 'evidence_refs': ['final_response','trajectory']}
