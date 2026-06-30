def evaluate(trace):
    tool_calls = trace.get('tool_calls') or []
    total = len(tool_calls)
    if total == 0:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls', 'evidence_refs': []}
    if total > 10:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'{total} tool calls exceeds cap of 10', 'evidence_refs': [{'total_calls': total}]}
    trajectory = trace.get('trajectory') or []
    import re
    refl_pat = re.compile(r'reflect|reflection|recap|summary so far|checkpoint|taking stock', re.IGNORECASE)
    # Build sequence of events: ('tool', idx) or ('note', text)
    events = []
    for step in trajectory:
        content = step.get('content') or ''
        tcs = step.get('tool_calls') or []
        if content and refl_pat.search(content):
            events.append(('note', content))
        for _ in tcs:
            events.append(('tool', None))
    # Walk: after every 3 tool calls, expect a reflection note before the next tool call (or at end)
    tool_count = 0
    missing_batches = []
    saw_note_after_batch = True
    for ev in events:
        if ev[0] == 'tool':
            if tool_count > 0 and tool_count % 3 == 0 and not saw_note_after_batch:
                missing_batches.append(tool_count)
            tool_count += 1
            saw_note_after_batch = False
        else:
            saw_note_after_batch = True
    # final batch check
    if tool_count > 0 and tool_count % 3 == 0 and not saw_note_after_batch:
        missing_batches.append(tool_count)
    if missing_batches:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'missing reflection note after batch(es) ending at tool call(s) {missing_batches}', 'evidence_refs': [{'total_calls': total, 'missing_batches': missing_batches}]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'{total} calls (<=10) with reflection notes after each batch of 3', 'evidence_refs': [{'total_calls': total}]}
