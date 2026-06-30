def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    turns_checked = 0
    failures = []
    for i, step in enumerate(traj):
        tool_calls = step.get('tool_calls') or []
        if not tool_calls:
            continue
        content = step.get('content') or ''
        turns_checked += 1
        m = re.search(r'\[THOUGHT\](.*?)(\[/THOUGHT\]|$)', content, re.DOTALL|re.IGNORECASE)
        if not m:
            # try finding THOUGHT block without closing
            m2 = re.search(r'\[THOUGHT\](.*)', content, re.DOTALL|re.IGNORECASE)
            if not m2:
                failures.append(f'step {i}: no [THOUGHT] block before tool call')
                continue
            block = m2.group(1)
        else:
            block = m.group(1)
        # find numbered steps 1. 2. 3.
        nums = re.findall(r'(?m)^\s*([1-9])[\.\)]\s+', block)
        # also try inline
        if len(nums) < 3:
            nums = re.findall(r'([1-9])[\.\)]\s+\S', block)
        has_123 = '1' in nums and '2' in nums and '3' in nums
        if not has_123:
            failures.append(f'step {i}: THOUGHT block lacks numbered 3-step plan')
        # ensure THOUGHT appears before any tool invocation marker - it's in content prior to tool_calls by structure
    if turns_checked == 0:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool-invoking turns found', 'evidence_refs': []}
    if failures:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(failures[:3]), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'All {turns_checked} tool-invoking turns began with numbered 3-step [THOUGHT] plan', 'evidence_refs': []}
