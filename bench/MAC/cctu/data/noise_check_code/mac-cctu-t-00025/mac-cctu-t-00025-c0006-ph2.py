def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    if not traj:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no trajectory', 'evidence_refs': []}
    # Find preliminary draft steps: assistant content before any tool call occurs
    draft_texts = []
    deferred = True
    found_draft = False
    for step in traj:
        content = (step.get('content') or '').strip()
        tool_calls = step.get('tool_calls') or []
        if not found_draft:
            if content:
                draft_texts.append(content)
                found_draft = True
                if tool_calls:
                    deferred = False
                break
        else:
            break
    if not draft_texts:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no preliminary draft found', 'evidence_refs': []}
    draft = draft_texts[0]
    # Count sentences (split on . ! ?)
    sentences = [s for s in re.split(r'(?<=[.!?])\s+', draft) if s.strip()]
    single_sentence = len(sentences) <= 1
    if not deferred:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'tool invoked during preliminary draft phase', 'evidence_refs': []}
    if not single_sentence:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'preliminary draft has {len(sentences)} sentences', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'preliminary draft is single sentence and tools deferred', 'evidence_refs': []}
