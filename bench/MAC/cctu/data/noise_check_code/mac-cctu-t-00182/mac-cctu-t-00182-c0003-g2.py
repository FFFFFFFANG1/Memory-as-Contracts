def evaluate(trace):
    import re
    trajectory = trace.get('trajectory') or []
    if not trajectory:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no trajectory', 'evidence_refs': []}
    pre_tool_text = ''
    first_tool_step = None
    for i, step in enumerate(trajectory):
        tcs = step.get('tool_calls') or []
        if tcs:
            first_tool_step = i
            break
        content = step.get('content') or ''
        if isinstance(content, str):
            pre_tool_text += '\n' + content
    if first_tool_step is None:
        # no tool calls; check final/any content for checklist
        text = pre_tool_text
        if not text.strip():
            text = trace.get('final_response') or ''
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        numbered = [l for l in lines if re.match(r'^(\d+)[\.\)]\s+', l)]
        if len(numbered) >= 2:
            return {'observed_followed': True, 'confidence': 'medium', 'reason': 'checklist present, no tools called', 'evidence_refs': []}
        return {'observed_followed': False, 'confidence': 'low', 'reason': 'no checklist found and no tools', 'evidence_refs': []}
    lines = [l.strip() for l in pre_tool_text.splitlines() if l.strip()]
    numbered = [l for l in lines if re.match(r'^(\d+)[\.\)]\s+', l)]
    nums = []
    for l in numbered:
        m = re.match(r'^(\d+)[\.\)]\s+', l)
        if m:
            nums.append(int(m.group(1)))
    if len(numbered) >= 2 and nums[:2] == [1,2]:
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'numbered checklist of {len(numbered)} items committed before first tool call', 'evidence_refs': [f'step:{first_tool_step}']}
    return {'observed_followed': False, 'confidence': 'high', 'reason': 'no numbered checklist found before first tool call', 'evidence_refs': [f'step:{first_tool_step}']}
