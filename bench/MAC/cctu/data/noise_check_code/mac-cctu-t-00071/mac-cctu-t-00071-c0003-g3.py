import re
def evaluate(trace):
    traj = trace.get('trajectory') or []
    pre_text = ''
    first_tool_step = None
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if tcs:
            first_tool_step = i
            break
        c = step.get('content') or ''
        if isinstance(c, str):
            pre_text += '\n' + c
    if first_tool_step is None:
        # no tool calls at all; check if any plan exists anyway
        if not pre_text.strip():
            return {'observed_followed': None, 'confidence':'unknown','reason':'No pre-tool content and no tool calls','evidence_refs':[]}
    # look for numbered list: at least 2 items like '1.' '2.' or '1)' '2)'
    lines = pre_text.splitlines()
    numbered = []
    for ln in lines:
        m = re.match(r'\s*(\d+)[\.\)]\s+\S', ln)
        if m:
            numbered.append(int(m.group(1)))
    has_plan = len(numbered) >= 2 and numbered[:2] == [1,2]
    if has_plan:
        return {'observed_followed': True, 'confidence':'high','reason':f'Found numbered plan with {len(numbered)} items before first tool call','evidence_refs':[]}
    return {'observed_followed': False, 'confidence':'medium','reason':'No numbered sub-question plan found before first tool call','evidence_refs':[]}
