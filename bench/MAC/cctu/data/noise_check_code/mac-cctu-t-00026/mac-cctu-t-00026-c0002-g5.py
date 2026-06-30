def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls in trajectory', 'evidence_refs': []}
    first_idx = None
    for i, step in enumerate(traj):
        if step.get('tool_calls'):
            first_idx = i
            break
    pre_text = ''
    if first_idx is None:
        for step in traj:
            pre_text += ' ' + (step.get('content') or '')
    else:
        for step in traj[:first_idx]:
            pre_text += ' ' + (step.get('content') or '')
        pre_text += ' ' + (traj[first_idx].get('content') or '')
    t = pre_text.lower()
    if not t.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No pre-tool planning text found', 'evidence_refs': []}
    sub_q_terms = ['sub-question','subquestion','sub question','sub-questions','decompos','break down','break it down','breakdown','plan:','steps:']
    dep_terms = ['tool','depend','will use','plan to use','expected tool','tools needed','will call','retrieval']
    has_sub = any(k in t for k in sub_q_terms) or len(re.findall(r'(?m)^\s*[-*\d\.\)]', pre_text)) >= 2
    has_dep = any(k in t for k in dep_terms)
    if has_sub and has_dep:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Pre-tool text contains decomposition and tool dependency mentions', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Missing {"decomposition" if not has_sub else ""} {"tool deps" if not has_dep else ""}'.strip(), 'evidence_refs': []}
