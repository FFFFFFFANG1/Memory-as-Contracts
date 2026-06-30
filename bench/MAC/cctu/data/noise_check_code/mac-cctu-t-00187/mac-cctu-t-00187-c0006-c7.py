def evaluate(trace):
    traj = trace.get('trajectory') or []
    if not traj:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no trajectory', 'evidence_refs': []}
    first = traj[0]
    content = (first.get('content') or '').strip()
    tool_calls = first.get('tool_calls') or []
    if tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'tool calls present in initial planning turn', 'evidence_refs': ['trajectory[0].tool_calls']}
    import re
    text = content.lower()
    roadmap_terms = ['plan','step','roadmap','decompos','approach','outline','first','then','next','1.','2.','- ']
    hits = sum(1 for t in roadmap_terms if t in text)
    if len(content) < 40 or hits < 2:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'first turn lacks visible decomposition roadmap', 'evidence_refs': ['trajectory[0].content']}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'first turn has written roadmap and no tool calls', 'evidence_refs': ['trajectory[0]']}
