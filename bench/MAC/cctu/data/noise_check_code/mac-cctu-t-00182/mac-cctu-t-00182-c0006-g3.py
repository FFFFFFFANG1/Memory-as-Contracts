def evaluate(trace):
    import re
    trajectory = trace.get('trajectory', []) or []
    if not trajectory:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No trajectory available', 'evidence_refs': []}
    # Identify planning phase: typically the first assistant step(s) before tool calls
    planning_step = None
    planning_idx = None
    for i, step in enumerate(trajectory):
        content = (step.get('content') or '').strip()
        if content:
            planning_step = step
            planning_idx = i
            break
    if planning_step is None:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'No planning/decomposition content found in trajectory', 'evidence_refs': []}
    content = planning_step.get('content') or ''
    tool_calls_in_planning = planning_step.get('tool_calls') or []
    # Check for numbered checklist pattern (1. 2. 3. or 1) 2) etc.)
    lines = [l.strip() for l in content.split('\n') if l.strip()]
    numbered = [l for l in lines if re.match(r'^\s*(\d+)[\.\)]\s+\S', l)]
    has_checklist = len(numbered) >= 2
    # Verify numbering is sequential starting at 1
    sequential = False
    if has_checklist:
        nums = []
        for l in numbered:
            m = re.match(r'^\s*(\d+)[\.\)]', l)
            if m:
                nums.append(int(m.group(1)))
        sequential = nums == list(range(1, len(nums)+1))
    no_tools = len(tool_calls_in_planning) == 0
    followed = has_checklist and sequential and no_tools
    reason_parts = []
    reason_parts.append(f'numbered_items={len(numbered)}')
    reason_parts.append(f'sequential={sequential}')
    reason_parts.append(f'tool_calls_in_planning_step={len(tool_calls_in_planning)}')
    return {'observed_followed': bool(followed), 'confidence': 'medium', 'reason': '; '.join(reason_parts), 'evidence_refs': [{'step_index': planning_idx}]}
