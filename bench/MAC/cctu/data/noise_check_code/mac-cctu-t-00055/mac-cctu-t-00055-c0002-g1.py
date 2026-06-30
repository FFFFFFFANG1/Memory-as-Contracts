def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    pre_text_parts = []
    found_tool = False
    for step in traj:
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if tcs:
            if content:
                pre_text_parts.append(content)
            found_tool = True
            break
        if content:
            pre_text_parts.append(content)
    if not found_tool:
        tc = trace.get('tool_calls') or []
        if not tc:
            return {'observed_followed': None, 'confidence':'unknown','reason':'No tool calls in trajectory; cannot assess pre-tool decomposition.','evidence_refs':[]}
    pre_text = '\n'.join(pre_text_parts)
    if not pre_text.strip():
        return {'observed_followed': False, 'confidence':'high','reason':'No content emitted before first tool call; numbered decomposition missing.','evidence_refs':[]}
    lines = [l.strip() for l in pre_text.splitlines() if l.strip()]
    numbered = [l for l in lines if re.match(r'^(\(?\d+[\).\:\-]|\d+\s)', l)]
    if len(numbered) < 2:
        return {'observed_followed': False, 'confidence':'medium','reason':'Fewer than 2 numbered items found in pre-tool content.','evidence_refs':[pre_text[:200]]}
    geo_terms = ['geolog','rock','mineral','volcan','mountain','fault','tecton','sediment','fossil','terrain','landform','plateau','basin','river','cave','crater','glacier','soil','strata','formation']
    cul_terms = ['cultur','tradition','heritage','folklore','myth','legend','ritual','festival','histor','people','communit','indigen','custom','religi','art','language','cuisine','architect']
    ok_items = 0
    for l in numbered:
        low = l.lower()
        if any(g in low for g in geo_terms) and any(c in low for c in cul_terms):
            ok_items += 1
    if ok_items >= max(2, len(numbered)//2 + (1 if len(numbered)%2 else 0)):
        return {'observed_followed': True, 'confidence':'medium','reason':f'Found {ok_items}/{len(numbered)} numbered items linking geological & cultural terms before first tool call.','evidence_refs':[pre_text[:300]]}
    return {'observed_followed': False, 'confidence':'medium','reason':f'Numbered list present but only {ok_items}/{len(numbered)} items express atomic geological-cultural linkage.','evidence_refs':[pre_text[:300]]}
