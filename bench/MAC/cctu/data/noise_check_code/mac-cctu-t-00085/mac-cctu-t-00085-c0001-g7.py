def evaluate(trace):
    import re
    calls = [c for c in trace.get('tool_calls', []) if c.get('name') == 'event_host_locator']
    text_blobs = []
    for step in trace.get('trajectory', []) or []:
        c = step.get('content')
        if isinstance(c, str):
            text_blobs.append(c)
    final = trace.get('final_response') or ''
    text_blobs.append(final)
    joined = '\n'.join(text_blobs).lower()
    ambiguity_markers = ['ambigu', 'unclear', 'multiple host', 'more than one host', 'conflict', 'disambiguat', 'which host', 'two cities', 'several cities']
    ambiguity = any(m in joined for m in ambiguity_markers)
    if not ambiguity:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No host-city ambiguity detected in trajectory; constraint may not apply.', 'evidence_refs': []}
    if len(calls) < 2:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Ambiguity indicated but event_host_locator was not called a second time.', 'evidence_refs': [{'tool_calls': len(calls)}]}
    second = calls[1]
    args = second.get('arguments') or {}
    args_str = ' '.join(f'{k}={v}' for k, v in args.items()).lower() if isinstance(args, dict) else str(args).lower()
    has_year = bool(re.search(r'year|\b(19|20)\d{2}\b|date|from|to|since|until', args_str))
    reconciled = any(w in joined for w in ['reconcile', 'reconciled', 'compared both', 'both outputs', 'combining results', 'cross-check'])
    if has_year and reconciled:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'Second event_host_locator call uses year filter and outputs reconciled in notes.', 'evidence_refs': [{'args': args}]}
    if has_year and not reconciled:
        return {'observed_followed': False, 'confidence': 'low', 'reason': 'Second call used year filter but reconciliation in working notes not evident.', 'evidence_refs': [{'args': args}]}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Second event_host_locator call lacks a refined year filter.', 'evidence_refs': [{'args': args}]}
