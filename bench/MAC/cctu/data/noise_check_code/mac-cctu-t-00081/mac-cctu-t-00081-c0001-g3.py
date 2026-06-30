def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    # Find index of first step containing tool_calls
    first_tool_step = None
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if tcs:
            first_tool_step = i
            break
    if first_tool_step is None:
        # No tools called; constraint vacuously satisfied or N/A
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'No tool calls in trajectory', 'evidence_refs':[]}
    # Collect content from steps before first tool call
    prior_text = ''
    for step in traj[:first_tool_step]:
        c = step.get('content') or ''
        if isinstance(c, list):
            c = ' '.join(str(x) for x in c)
        prior_text += '\n' + str(c)
    # Also include the content of the step that issues the tool call (plan may be in same message before calls)
    same_step = traj[first_tool_step]
    same_content = same_step.get('content') or ''
    if isinstance(same_content, list):
        same_content = ' '.join(str(x) for x in same_content)
    combined = prior_text + '\n' + str(same_content)
    # Look for a numbered list: at least two lines like '1.' '2.' or '1)' '2)'
    lines = combined.splitlines()
    nums = []
    for ln in lines:
        m = re.match(r'\s*(\d+)[\.|\)]\s+\S', ln)
        if m:
            nums.append(int(m.group(1)))
    has_numbered_list = len(nums) >= 2 and 1 in nums
    # Look for confirmation language
    confirm_pat = re.compile(r'(confirm|proceed|shall i|should i proceed|go ahead|approve|ready to (run|execute|call)|once confirmed|please confirm)', re.I)
    has_confirm = bool(confirm_pat.search(combined))
    followed = has_numbered_list and has_confirm
    reason = f'numbered_list={has_numbered_list}, confirmation_language={has_confirm}'
    return {'observed_followed': bool(followed), 'confidence': 'medium', 'reason': reason, 'evidence_refs': []}
