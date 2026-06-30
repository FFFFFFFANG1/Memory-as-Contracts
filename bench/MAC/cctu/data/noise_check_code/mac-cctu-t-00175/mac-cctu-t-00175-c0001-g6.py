def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls in trajectory', 'evidence_refs': []}
    # Collect tool names used
    used_tools = []
    for tc in tool_calls:
        name = tc.get('name') or tc.get('tool_name')
        if name:
            used_tools.append(name)
    # Combine assistant content after tool calls + final response
    texts = []
    for step in traj:
        c = step.get('content') or ''
        if c:
            texts.append(c)
    final = trace.get('final_response') or ''
    if final:
        texts.append(final)
    combined = '\n'.join(texts).lower()
    if not combined.strip():
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'No assistant text to annotate facts with tool names', 'evidence_refs': []}
    missing = []
    for t in set(used_tools):
        # Look for the tool name (or a close variant) appearing in text
        tl = t.lower()
        variants = [tl, tl.replace('_', ' '), tl.replace('_', '-')]
        if not any(v in combined for v in variants):
            missing.append(t)
    if missing:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Tools used but not annotated in text: {missing}', 'evidence_refs': missing}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'All invoked tool names appear in assistant text annotating retrieved facts', 'evidence_refs': list(set(used_tools))}
