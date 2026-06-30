def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    if not traj:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no trajectory', 'evidence_refs': []}
    first = traj[0]
    content = (first.get('content') or '').strip()
    tool_calls = first.get('tool_calls') or []
    if tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'first turn invoked tools instead of emitting roadmap', 'evidence_refs': ['trajectory[0].tool_calls']}
    if not content:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'first assistant turn has no content', 'evidence_refs': ['trajectory[0]']}
    lines = [l.strip() for l in content.splitlines() if l.strip()]
    numbered = [l for l in lines if re.match(r'^(\(?\d+[\.\)\:]|\d+\s)', l)]
    if len(numbered) >= 2:
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'first turn contains {len(numbered)} numbered roadmap items', 'evidence_refs': ['trajectory[0].content']}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'first turn lacks explicit numbered sub-task roadmap', 'evidence_refs': ['trajectory[0].content']}
