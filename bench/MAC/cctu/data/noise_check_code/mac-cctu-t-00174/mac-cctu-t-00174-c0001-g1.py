def evaluate(trace):
    traj = trace.get('trajectory') or []
    if not traj:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no trajectory','evidence_refs':[]}
    pre_text = ''
    found_tool = False
    pre_had_content = False
    for step in traj:
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if tcs:
            found_tool = True
            # include content on same step prior to tools
            if content:
                pre_text += '\n' + content
                pre_had_content = True
            break
        else:
            if content:
                pre_text += '\n' + content
                pre_had_content = True
    if not found_tool:
        # No tools called; constraint about pre-tool decomposition trivially holds if listed, else unknown
        if not pre_had_content:
            return {'observed_followed': None,'confidence':'unknown','reason':'no tools and no content','evidence_refs':[]}
    if not pre_had_content:
        return {'observed_followed': False,'confidence':'high','reason':'tool invoked before any decomposition text','evidence_refs':[]}
    lines = [l.strip() for l in pre_text.splitlines() if l.strip()]
    q_lines = [l for l in lines if l.endswith('?')]
    bullet_lines = []
    import re
    for l in lines:
        if re.match(r'^([-*\u2022]|\d+[\.)]|[a-zA-Z][\.)])\s+', l):
            bullet_lines.append(l)
    sub_items = q_lines if len(q_lines) >= 2 else bullet_lines
    if len(sub_items) >= 2:
        return {'observed_followed': True,'confidence':'medium','reason':f'found {len(sub_items)} sub-question lines before tool call','evidence_refs':[]}
    return {'observed_followed': False,'confidence':'medium','reason':'no multi-line decomposition list found before tool call','evidence_refs':[]}
