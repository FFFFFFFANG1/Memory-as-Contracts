import re
def evaluate(trace):
    traj = trace.get('trajectory') or []
    pre_text = ''
    first_tool_idx = None
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if tcs:
            first_tool_idx = i
            break
        c = step.get('content')
        if isinstance(c, str):
            pre_text += '\n' + c
    if first_tool_idx is None:
        if not pre_text.strip():
            return {'observed_followed': None, 'confidence':'unknown', 'reason':'No tool calls and no pre-content', 'evidence_refs':[]}
    lines = [l.strip() for l in pre_text.splitlines() if l.strip()]
    numbered = [l for l in lines if re.match(r'^(\(?\d+[\).\:\-]|\d+\s)', l)]
    if len(numbered) >= 2:
        return {'observed_followed': True, 'confidence':'high', 'reason': f'Found {len(numbered)} numbered items before first tool call', 'evidence_refs':[]}
    return {'observed_followed': False, 'confidence':'medium', 'reason':'No explicit numbered decomposition before first tool call', 'evidence_refs':[]}
