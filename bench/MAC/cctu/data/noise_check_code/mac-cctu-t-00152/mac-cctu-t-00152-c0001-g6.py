def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    pre_text = ''
    found_first_tool = False
    for step in traj:
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if tcs:
            pre_text += '\n' + content
            found_first_tool = True
            break
        pre_text += '\n' + content
    if not found_first_tool:
        tcs_all = trace.get('tool_calls') or []
        if not tcs_all:
            return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls in trajectory', 'evidence_refs': []}
    if not pre_text.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no content before first tool call', 'evidence_refs': []}
    numbered = re.findall(r'(?m)^\s*(\d+)[\.\)]\s+\S', pre_text)
    has_numbered = len(set(numbered)) >= 2
    low = pre_text.lower()
    mentions_dep = any(k in low for k in ['depend', 'prerequisite', 'after ', 'before ', 'requires', 'sequential', 'parallel', 'concurrent', 'independent'])
    if has_numbered and mentions_dep:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'numbered decomposition with dependency/parallel language before first tool call', 'evidence_refs': []}
    if has_numbered:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'numbered list present but no dependency/parallel discussion', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'high', 'reason': 'no numbered decomposition before first tool call', 'evidence_refs': []}
