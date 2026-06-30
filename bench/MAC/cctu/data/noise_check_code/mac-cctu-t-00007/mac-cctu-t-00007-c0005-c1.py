def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    pre_text_parts = []
    found_tool = False
    first_tool_iter = None
    for step in traj:
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if tcs:
            found_tool = True
            if content:
                pre_text_parts.append(content)
            break
        if content:
            pre_text_parts.append(content)
    if not found_tool:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls issued; cannot evaluate pre-tool decomposition.', 'evidence_refs': []}
    text = '\n'.join(pre_text_parts)
    if not text.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No content emitted before first tool call; numbered decomposition missing.', 'evidence_refs': []}
    lines = [l.rstrip() for l in text.splitlines()]
    numbered = [l for l in lines if re.match(r'^\s*\d+[\.\)]\s+\S', l)]
    if len(numbered) >= 2:
        nums = []
        for l in numbered:
            m = re.match(r'^\s*(\d+)', l)
            if m: nums.append(int(m.group(1)))
        seq_ok = any(nums[i+1]-nums[i]==1 for i in range(len(nums)-1)) if len(nums)>=2 else False
        if seq_ok or nums[:1]==[1]:
            return {'observed_followed': True, 'confidence': 'high', 'reason': f'Found numbered list of {len(numbered)} items before first tool call.', 'evidence_refs': numbered[:5]}
        return {'observed_followed': True, 'confidence': 'medium', 'reason': f'Found {len(numbered)} numbered items before first tool call.', 'evidence_refs': numbered[:5]}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Did not detect a numbered bullet list (>=2 items) before first tool call.', 'evidence_refs': lines[:5]}
