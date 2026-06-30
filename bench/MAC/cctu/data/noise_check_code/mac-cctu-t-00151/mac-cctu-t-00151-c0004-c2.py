def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls in trajectory', 'evidence_refs': []}
    # Find first tool call iteration/index
    first_tc = tool_calls[0]
    first_iter = first_tc.get('iteration', 0)
    first_index = first_tc.get('index', 0)
    # Collect assistant text BEFORE first tool call
    pre_text_parts = []
    for step in traj:
        step_iter = step.get('iteration', 0)
        content = step.get('content') or ''
        calls = step.get('tool_calls') or []
        if step_iter < first_iter:
            if content:
                pre_text_parts.append(content)
        elif step_iter == first_iter:
            # Same iteration as first call: include content if it appears before the call
            if content:
                pre_text_parts.append(content)
            break
        else:
            break
    pre_text = '\n'.join(pre_text_parts)
    if not pre_text.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No written content before first tool call', 'evidence_refs': []}
    # Determine intended tools = tools actually called (proxy for 'every intended tool')
    intended_tools = []
    seen = set()
    for tc in tool_calls:
        n = tc.get('name')
        if n and n not in seen:
            seen.add(n)
            intended_tools.append(n)
    low = pre_text.lower()
    # Check outline indicators
    outline_markers = ['step', 'plan', 'outline', 'decompos', 'sub-task', 'subtask', '1.', '2.', '- ', '* ']
    has_outline = any(m in low for m in outline_markers)
    missing = [t for t in intended_tools if t.lower() not in low]
    if not has_outline:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'No outline/decomposition markers found before first tool call', 'evidence_refs': [pre_text[:200]]}
    if missing:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Outline missing tools: {missing}', 'evidence_refs': [pre_text[:300]]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'Outline present listing all intended tools before first retrieval call', 'evidence_refs': [pre_text[:200]]}
