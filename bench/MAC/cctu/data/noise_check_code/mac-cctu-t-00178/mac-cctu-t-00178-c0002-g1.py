def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No data-retrieval tools invoked; cannot assess planning precedence.', 'evidence_refs': []}
    first_iter = min((tc.get('iteration', tc.get('index', 0)) for tc in tool_calls), default=None)
    pre_text_parts = []
    for step in traj:
        it = step.get('iteration', step.get('index', 0))
        has_tc = bool(step.get('tool_calls'))
        if first_iter is not None and it is not None and it > first_iter:
            continue
        if has_tc and it == first_iter:
            content = step.get('content') or ''
            pre_text_parts.append(content)
            continue
        content = step.get('content') or ''
        if content:
            pre_text_parts.append(content)
    pre_text = '\n'.join(pre_text_parts)
    if not pre_text.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No written planning content before first data-retrieval tool call.', 'evidence_refs': []}
    low = pre_text.lower()
    decomp_terms = ['sub-task', 'subtask', 'sub task', 'decomposition', 'decompose', 'break down', 'breakdown', 'steps:', 'plan:']
    dep_terms = ['dependency', 'dependencies', 'depends on', 'tool-dependency', 'tool dependency', 'dependency map', 'tool map', '->', '→']
    has_decomp = any(t in low for t in decomp_terms)
    has_dep = any(t in low for t in dep_terms)
    if has_decomp and has_dep:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Pre-tool planning includes sub-task decomposition and tool-dependency map indicators.', 'evidence_refs': []}
    missing = []
    if not has_decomp: missing.append('sub-task decomposition')
    if not has_dep: missing.append('tool-dependency map')
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Pre-tool planning missing: ' + ', '.join(missing) + '.', 'evidence_refs': []}
