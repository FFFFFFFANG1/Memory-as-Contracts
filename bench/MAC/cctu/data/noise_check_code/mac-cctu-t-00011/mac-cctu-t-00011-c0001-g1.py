def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'No tool calls in trajectory','evidence_refs':[]}
    pre_text = ''
    found_pre = False
    for step in traj:
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if tcs:
            if content:
                pre_text += '\n' + content
            found_pre = True
            break
        if content:
            pre_text += '\n' + content
    if not pre_text.strip():
        return {'observed_followed': False, 'confidence':'high','reason':'No textual content before first tool call','evidence_refs':[]}
    # Look for numbered list with at least 2 items (1. ... 2. ...)
    lines = pre_text.splitlines()
    nums = []
    for ln in lines:
        m = re.match(r'\s*(\d+)[\.\)]\s+\S', ln)
        if m:
            nums.append(int(m.group(1)))
    has_sequence = len(nums) >= 2 and nums[0] == 1 and all(nums[i]-nums[i-1]==1 for i in range(1,len(nums)))
    if has_sequence:
        return {'observed_followed': True, 'confidence':'high','reason':f'Found numbered decomposition with {len(nums)} items before first tool call','evidence_refs':[]}
    # fallback: inline numbered like '1) ... 2) ...' on single line
    inline = re.findall(r'(?:^|\s)(\d+)[\.\)]\s+', pre_text)
    inline_nums = [int(x) for x in inline]
    if len(inline_nums) >= 2 and inline_nums[0]==1 and all(inline_nums[i]-inline_nums[i-1]==1 for i in range(1,len(inline_nums))):
        return {'observed_followed': True, 'confidence':'medium','reason':'Found inline numbered decomposition','evidence_refs':[]}
    return {'observed_followed': False, 'confidence':'high','reason':'No numbered decomposition of sub-tasks found before first tool call','evidence_refs':[]}
