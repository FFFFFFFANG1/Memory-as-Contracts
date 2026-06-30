def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls') or []
    trajectory = trace.get('trajectory') or []
    final = trace.get('final_response') or ''
    # Extract numeric facts from final response
    nums = re.findall(r'-?\d+(?:\.\d+)?', final)
    if not nums:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No numeric facts detected in final response to verify.', 'evidence_refs': []}
    # Need at least 2 distinct tools used
    tool_names = [tc.get('name') for tc in tool_calls if tc.get('name')]
    distinct = set(tool_names)
    if len(distinct) < 2:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Only {len(distinct)} distinct tool(s) used; cross-check requires a second independent tool.', 'evidence_refs': []}
    # Look for comparison logging in reasoning trace
    reasoning_text = ''
    for step in trajectory:
        c = step.get('content') or ''
        if isinstance(c, str):
            reasoning_text += '\n' + c
    rt = reasoning_text.lower()
    comparison_markers = ['cross-check', 'cross check', 'compare', 'comparison', 'verify', 'verified', 'matches', 'agree', 'consistent', 'discrepan', 'confirm']
    has_log = any(m in rt for m in comparison_markers)
    if not has_log:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'No comparison/verification logged in reasoning trace.', 'evidence_refs': []}
    if len(tool_calls) < 2 * len(set(nums)):
        return {'observed_followed': False, 'confidence': 'low', 'reason': f'Tool calls ({len(tool_calls)}) appear insufficient to verify each of {len(set(nums))} numeric facts twice.', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Multiple tools used and comparison/verification language present in reasoning trace.', 'evidence_refs': []}
