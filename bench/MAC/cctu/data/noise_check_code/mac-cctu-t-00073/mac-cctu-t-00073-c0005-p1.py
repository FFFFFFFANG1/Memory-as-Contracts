def evaluate(trace):
    import re
    trajectory = trace.get('trajectory') or []
    pre_tool_texts = []
    found_tool = False
    for step in trajectory:
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if tcs:
            if content:
                pre_tool_texts.append(content)
            found_tool = True
            break
        if content:
            pre_tool_texts.append(content)
    if not found_tool:
        tcs_flat = trace.get('tool_calls') or []
        if not tcs_flat:
            return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found in trajectory.', 'evidence_refs': []}
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'Could not locate pre-tool assistant content in trajectory steps.', 'evidence_refs': []}
    combined = '\n'.join(pre_tool_texts)
    if not combined.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No assistant text precedes the first tool call; no numbered decomposition was provided.', 'evidence_refs': []}
    numbered = re.findall(r'(?m)^\s*(\d+)[\.\)]\s+\S', combined)
    nums = [int(n) for n in numbered]
    if len(nums) >= 2 and nums[0] == 1 and all(nums[i+1] - nums[i] == 1 for i in range(len(nums)-1)):
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'Found numbered sub-task list with {len(nums)} items before first tool call.', 'evidence_refs': []}
    if len(nums) >= 2:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': f'Numbered list present ({nums}) before first tool call, though not strictly sequential from 1.', 'evidence_refs': []}
    if len(nums) == 1:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Only one numbered item found; sub-tasks were not enumerated as a list.', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'high', 'reason': 'No numbered list detected in pre-tool assistant content.', 'evidence_refs': []}
