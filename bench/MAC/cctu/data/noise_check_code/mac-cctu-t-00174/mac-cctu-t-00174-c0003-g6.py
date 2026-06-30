def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    pre_text = ''
    found_tool_call = False
    for step in traj:
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if tcs:
            found_tool_call = True
            break
        pre_text += '\n' + content
    if not found_tool_call:
        # No tool calls were issued; constraint about 'before any tool call' is vacuous
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found in trajectory.', 'evidence_refs': []}
    if not pre_text.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No pre-tool-call content enumerating sub-questions.', 'evidence_refs': []}
    # Detect numbered list items (1., 2., or 1) 2))
    numbered = re.findall(r'(?m)^\s*(\d+)[\.\)]\s+.+', pre_text)
    if len(numbered) < 2:
        # Could still be a single sub-question; check at least one numbered item
        if len(numbered) < 1:
            return {'observed_followed': False, 'confidence': 'high', 'reason': 'No numbered list of sub-questions found before tool calls.', 'evidence_refs': []}
    # Check that tools are identified - look for mentions of available tool names in pre_text
    tools = trace.get('tool_calls') or []
    used_tool_names = set()
    for tc in tools:
        n = tc.get('name')
        if n:
            used_tool_names.add(n)
    mentioned = [t for t in used_tool_names if t.lower() in pre_text.lower()]
    # Also accept generic mention via 'tool' keyword next to items
    tool_word_count = len(re.findall(r'(?i)tool', pre_text))
    items_count = len(numbered)
    if len(mentioned) >= max(1, len(used_tool_names)//2) or tool_word_count >= items_count:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': f'Found {items_count} numbered items with tool identification before tool calls.', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Numbered list present but tools per item not clearly identified.', 'evidence_refs': []}
