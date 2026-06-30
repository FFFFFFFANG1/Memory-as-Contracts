def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    pre_tool_text = ''
    found_tool = False
    for step in traj:
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if tcs:
            found_tool = True
            if content and not pre_tool_text:
                pre_tool_text = content
            break
        if content:
            pre_tool_text += ('\n' if pre_tool_text else '') + content
    if not pre_tool_text.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No pre-tool assistant text found before first tool call.', 'evidence_refs': []}
    text = pre_tool_text.strip()
    if any(m in text for m in ['```','**','##','__']):
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Pre-tool text contains markdown formatting.', 'evidence_refs': []}
    # Take first non-empty line/paragraph as the summary
    first_block = re.split(r'\n\s*\n', text)[0].strip()
    # Count sentences roughly
    sentences = [s for s in re.split(r'(?<=[.!?])\s+', first_block) if s.strip()]
    if len(sentences) != 1:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Expected one sentence, found {len(sentences)}.', 'evidence_refs':[first_block[:200]]}
    low = first_block.lower()
    has_park = 'park' in low
    has_forest = 'forest' in low
    if not (has_park and has_forest):
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Pre-tool sentence missing park or forest reference.', 'evidence_refs':[first_block[:200]]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Single plain-text sentence before first tool naming park and forest.', 'evidence_refs':[first_block[:200]]}
