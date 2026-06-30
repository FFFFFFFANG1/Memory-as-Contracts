def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    pre_text = []
    first_tool_idx = None
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if tcs:
            first_tool_idx = i
            if content:
                pre_text.append(content)
            break
        if content:
            pre_text.append(content)
    if first_tool_idx is None:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls in trajectory', 'evidence_refs': []}
    text = '\n'.join(pre_text)
    if not text.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No assistant content before first tool call; roadmap missing', 'evidence_refs': [{'step_index': first_tool_idx}]}
    # look for numbered list: at least two of patterns like '1.' '2.' or '1)' '2)'
    nums = re.findall(r'(?m)^\s*(\d+)[\.)]\s+\S', text)
    distinct = sorted(set(int(n) for n in nums))
    has_roadmap = len(distinct) >= 2 and 1 in distinct and 2 in distinct
    if has_roadmap:
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'Found numbered roadmap items {distinct} before first tool call', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'No explicit numbered roadmap (e.g., 1. 2. ...) found before first tool call', 'evidence_refs': []}
