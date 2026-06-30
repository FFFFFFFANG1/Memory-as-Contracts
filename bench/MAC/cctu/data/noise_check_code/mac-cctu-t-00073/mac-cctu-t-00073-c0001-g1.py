def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    terms = ['conservationist','reserve','ecosystem','species','zoologist','city','festival']
    pre_text = ''
    found_tool = False
    for step in traj:
        content = step.get('content') or ''
        tcs = step.get('tool_calls') or []
        if tcs:
            pre_text += '\n' + content
            found_tool = True
            break
        pre_text += '\n' + content
    if not found_tool:
        tcs_flat = trace.get('tool_calls') or []
        if not tcs_flat:
            return {'observed_followed': None, 'confidence':'unknown','reason':'No tool calls found; cannot assess pre-tool decomposition.','evidence_refs':[]}
        pre_text = '\n'.join((s.get('content') or '') for s in traj)
    text = pre_text
    low = text.lower()
    # Check numbered list: at least 7 numbered items
    numbered = re.findall(r'(?m)^\s*(?:\d+[\.\)]|\(\d+\))\s+.+', text)
    has_numbering = len(numbered) >= 7
    # Check checklist style (optional but constraint says checklist)
    checklist_markers = re.findall(r'(?m)^\s*(?:\d+[\.\)]\s*)?\[[ xX]\]', text)
    has_checklist = len(checklist_markers) >= 7 or bool(re.search(r'checklist', low))
    missing = [t for t in terms if t not in low]
    followed = has_numbering and not missing and has_checklist
    reason = f'numbered_items={len(numbered)}, missing_terms={missing}, checklist_markers={len(checklist_markers)}'
    return {'observed_followed': bool(followed), 'confidence':'medium' if found_tool else 'low','reason':reason,'evidence_refs':[]}
