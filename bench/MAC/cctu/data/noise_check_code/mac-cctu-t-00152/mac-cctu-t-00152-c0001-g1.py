def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    pre_text = ''
    found_tool = False
    for step in traj:
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if tcs:
            pre_text += '\n' + content
            found_tool = True
            break
        pre_text += '\n' + content
    if not found_tool and not pre_text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'No pre-tool content found','evidence_refs':[]}
    lines = [l.strip() for l in pre_text.splitlines() if l.strip()]
    topics = {
        'aqueduct': ['aqueduct'],
        'author_novel': ['novel','author','book','literary'],
        'lunar': ['lunar','moon','landing']
    }
    matched = {}
    for key, kws in topics.items():
        for i, line in enumerate(lines):
            low = line.lower()
            if any(k in low for k in kws):
                matched[key] = i
                break
    if len(matched) < 3:
        return {'observed_followed': False, 'confidence':'high','reason':f'Missing sub-questions in pre-tool content; matched={list(matched.keys())}','evidence_refs':[]}
    idxs = list(matched.values())
    if len(set(idxs)) < 3:
        return {'observed_followed': False,'confidence':'high','reason':'Sub-questions not on separate lines','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'high','reason':'All three sub-questions listed on separate lines before any tool call','evidence_refs':[]}
