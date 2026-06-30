def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    pre_text = ''
    first_tool_iter = None
    for step in traj:
        if step.get('tool_calls'):
            first_tool_iter = step.get('iteration', 0)
            break
        c = step.get('content') or ''
        pre_text += '\n' + c
    if first_tool_iter is None and not pre_text:
        return {'observed_followed': None, 'confidence':'unknown','reason':'No pre-tool content and no tool calls','evidence_refs':[]}
    # Find numbered items like '1.' '2.' '1)' '2)' on separate lines or inline
    nums = re.findall(r'(?m)(?:^|\n)\s*(\d+)[\.\)]\s+\S', pre_text)
    unique_nums = []
    for n in nums:
        if n not in unique_nums:
            unique_nums.append(n)
    has_plan = len(unique_nums) >= 2 and unique_nums[0] == '1'
    if not has_plan:
        return {'observed_followed': False, 'confidence':'high','reason':f'No numbered decomposition plan found before first tool call (found numbers: {unique_nums})','evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'high','reason':f'Numbered plan with items {unique_nums} appeared before any tool call','evidence_refs':[]}
