def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls in trajectory', 'evidence_refs': []}
    # Find the first assistant message that contains tool calls
    first_tool_idx = None
    for i, step in enumerate(traj):
        if step.get('tool_calls'):
            first_tool_idx = i
            break
    if first_tool_idx is None:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'Tool calls present but not located in trajectory', 'evidence_refs': []}
    # Collect content before first tool call (including same step content)
    pre_text_parts = []
    for j in range(0, first_tool_idx + 1):
        c = traj[j].get('content') or ''
        if isinstance(c, list):
            c = ' '.join(str(x) for x in c)
        pre_text_parts.append(str(c))
    pre_text = '\n'.join(pre_text_parts)
    if not pre_text.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No textual plan produced before first tool call', 'evidence_refs': []}
    planned_tool_names = []
    seen = set()
    for tc in tool_calls:
        n = tc.get('name')
        if n and n not in seen:
            seen.add(n)
            planned_tool_names.append(n)
    low = pre_text.lower()
    mentioned = [t for t in planned_tool_names if t.lower() in low]
    coverage = len(mentioned) / max(1, len(planned_tool_names))
    # Look for decomposition cues and 'return/expect/provide' language
    plan_cues = ['plan', 'sub-task', 'subtask', 'decomposition', 'steps:', 'step 1', 'first,', 'i will', 'i\'ll']
    expect_cues = ['return', 'expect', 'provide', 'retrieve', 'get', 'yield', 'output']
    has_plan_cue = any(k in low for k in plan_cues)
    has_expect_cue = any(k in low for k in expect_cues)
    followed = coverage >= 0.6 and has_expect_cue and (has_plan_cue or len(planned_tool_names) <= 1)
    reason = f'coverage={coverage:.2f}, plan_cue={has_plan_cue}, expect_cue={has_expect_cue}, mentioned={mentioned}, planned={planned_tool_names}'
    return {'observed_followed': bool(followed), 'confidence': 'medium', 'reason': reason, 'evidence_refs': []}
