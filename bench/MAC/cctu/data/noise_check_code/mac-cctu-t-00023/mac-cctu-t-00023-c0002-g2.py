def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls','evidence_refs':[]}
    first = calls[0].get('name')
    if first != 'historical_event_data_retriever':
        return {'observed_followed': False,'confidence':'high','reason': f'first tool was {first}, not historical_event_data_retriever','evidence_refs':[{'index':calls[0].get('index'),'name':first}]}
    # Check notes: look at assistant content for bullet lists labeled as scoping notes
    import re
    traj = trace.get('trajectory') or []
    for step in traj:
        content = (step.get('content') or '')
        if not content:
            continue
        low = content.lower()
        if 'scoping' in low or 'preliminary' in low:
            # find bullet blocks
            lines = content.splitlines()
            bullet_block = []
            blocks = []
            for ln in lines:
                if re.match(r'^\s*[-*\u2022]\s+', ln):
                    bullet_block.append(ln)
                else:
                    if bullet_block:
                        blocks.append(bullet_block)
                        bullet_block = []
            if bullet_block:
                blocks.append(bullet_block)
            for b in blocks:
                if len(b) > 5:
                    return {'observed_followed': False,'confidence':'medium','reason': f'scoping notes bullet block has {len(b)} lines (>5)','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'high','reason':'historical_event_data_retriever invoked first; no over-long scoping bullet blocks detected','evidence_refs':[{'index':calls[0].get('index'),'name':first}]}
