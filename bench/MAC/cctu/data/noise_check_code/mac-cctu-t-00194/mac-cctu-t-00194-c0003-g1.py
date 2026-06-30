def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'No tool calls present','evidence_refs':[]}
    # Find content before first tool call
    pre_text = ''
    first_tool_iter = None
    for tc in tool_calls:
        it = tc.get('iteration')
        if it is not None:
            first_tool_iter = it if first_tool_iter is None else min(first_tool_iter, it)
    for step in traj:
        it = step.get('iteration')
        content = step.get('content') or ''
        has_tc = bool(step.get('tool_calls'))
        if first_tool_iter is not None and it is not None and it < first_tool_iter:
            pre_text += '\n' + content
        elif first_tool_iter is not None and it == first_tool_iter and not has_tc:
            pre_text += '\n' + content
        elif first_tool_iter is not None and it == first_tool_iter and has_tc:
            pre_text += '\n' + content
            break
    if not pre_text.strip():
        return {'observed_followed': False, 'confidence':'high','reason':'No pre-tool content found before first tool invocation','evidence_refs':[]}
    lines = [l.strip() for l in pre_text.splitlines() if l.strip()]
    bullet_re = re.compile(r'^([-*+•]|\d+[.)])\s+')
    bullets = [l for l in lines if bullet_re.match(l)]
    if len(bullets) < 2:
        return {'observed_followed': False, 'confidence':'high','reason':f'Found {len(bullets)} bullet lines before first tool call; expected a bullet-point outline','evidence_refs':[]}
    low = pre_text.lower()
    mentions_tools = any(k in low for k in ['tool','category','categor','finder','calculator','identifier','locator','retriever','analyzer','inquiry'])
    if not mentions_tools:
        return {'observed_followed': False, 'confidence':'medium','reason':'Bullet outline present but does not appear to mention required tool categories','evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'high','reason':f'Pre-tool bullet outline with {len(bullets)} bullets mentioning tool categories','evidence_refs':[]}
