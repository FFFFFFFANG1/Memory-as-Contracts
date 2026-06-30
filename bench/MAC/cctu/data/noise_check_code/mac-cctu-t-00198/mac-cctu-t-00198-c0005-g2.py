def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls to log','evidence_refs':[]}
    # Collect intermediate assistant texts (steps that contain tool_calls or precede final)
    intermediate_texts = []
    for i, step in enumerate(traj):
        content = step.get('content') or ''
        if not content:
            continue
        # treat as intermediate if it has tool_calls or is not last step
        if step.get('tool_calls') or i < len(traj)-1:
            intermediate_texts.append(content)
    if not intermediate_texts:
        return {'observed_followed': False,'confidence':'medium','reason':'no intermediate scratch logging found','evidence_refs':[]}
    combined = '\n'.join(intermediate_texts)
    # Heuristic: scratch table indicated by pipes/rows or explicit 'scratch' wording
    has_table = ('|' in combined and combined.count('|') >= 4) or bool(re.search(r'scratch', combined, re.I))
    # raw tool-call identifiers: look for call_ ids or index references
    ids_in_calls = []
    for tc in tool_calls:
        for k in ('id','call_id','tool_call_id'):
            v = tc.get(k)
            if v:
                ids_in_calls.append(str(v))
    has_ids = False
    if ids_in_calls:
        has_ids = any(tid in combined for tid in ids_in_calls)
    else:
        # fallback: references to tool names with index/iteration markers
        has_ids = bool(re.search(r'(call[_-]?\d+|#\d+|\bindex\s*[:=]\s*\d+|\bid\s*[:=])', combined, re.I))
    # answer prose detection in intermediate: long narrative sentences concluding the answer
    prose_markers = re.search(r'(final answer|the answer is|in conclusion|therefore,? the)', combined, re.I)
    drafted_answer = bool(prose_markers)
    followed = has_table and has_ids and not drafted_answer
    reason = f'table={has_table}, ids={has_ids}, prose_drafted={drafted_answer}'
    return {'observed_followed': bool(followed), 'confidence':'medium','reason':reason,'evidence_refs':[]}
