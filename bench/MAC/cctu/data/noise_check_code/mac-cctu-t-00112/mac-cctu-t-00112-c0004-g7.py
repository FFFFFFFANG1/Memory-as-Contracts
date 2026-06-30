def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    # Find the first assistant step
    first_step = None
    for step in traj:
        if step.get('role') in (None,'assistant') or step.get('tool_calls') is not None or step.get('content'):
            first_step = step
            break
    if first_step is None:
        fr = trace.get('final_response')
        if not fr:
            return {'observed_followed': None, 'confidence':'unknown','reason':'no trajectory or response','evidence_refs':[]}
        content = fr
        had_tools_before = False
    else:
        content = first_step.get('content') or ''
        had_tools_before = bool(first_step.get('tool_calls'))
    # Check the pre-tool content of the first step contains a numbered roadmap
    text = content.strip() if isinstance(content,str) else ''
    # If content empty but tool_calls present in first step -> no roadmap before tools
    if not text and had_tools_before:
        return {'observed_followed': False,'confidence':'high','reason':'first step invoked tools without any preceding content/roadmap','evidence_refs':['trajectory[0]']}
    # Look for numbered list at the opening: lines like '1.' '1)' '1:' within first ~400 chars
    head = text[:1000]
    # Require at least items '1' and '2' to count as numbered roadmap
    pat1 = re.search(r'(^|\n)\s*1[\.\)\:]\s+\S', head)
    pat2 = re.search(r'(^|\n)\s*2[\.\)\:]\s+\S', head)
    if pat1 and pat2:
        # Ensure the numbered list appears before any prose that follows tool output references; just confirm it opens
        # Find position of first numbered item
        m = re.search(r'(^|\n)\s*1[\.\)\:]\s+', text)
        prefix = text[:m.start()] if m else ''
        # Allow a short intro sentence (<=200 chars) before the list
        if len(prefix.strip()) <= 200:
            return {'observed_followed': True,'confidence':'high','reason':'first reply opens with numbered roadmap (items 1 and 2 found before tools)','evidence_refs':['trajectory[0].content']}
        else:
            return {'observed_followed': False,'confidence':'medium','reason':'numbered list exists but not at opening','evidence_refs':['trajectory[0].content']}
    return {'observed_followed': False,'confidence':'high','reason':'no numbered roadmap (items 1 and 2) detected at opening of first reply','evidence_refs':['trajectory[0].content']}
