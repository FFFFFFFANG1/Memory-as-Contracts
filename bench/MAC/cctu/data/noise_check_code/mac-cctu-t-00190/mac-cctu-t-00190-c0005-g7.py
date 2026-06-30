def evaluate(trace):
    import re
    calls = trace.get('tool_calls', []) or []
    offending = []
    saw_superior_context = False
    for c in calls:
        name = (c.get('name') or '').lower()
        args = c.get('arguments') or {}
        try:
            args_str = ' '.join(str(v) for v in args.values()) if isinstance(args, dict) else str(args)
        except Exception:
            args_str = str(args)
        if 'superior' in args_str.lower():
            saw_superior_context = True
            if name == 'island_counter':
                offending.append(c.get('index'))
    final = (trace.get('final_response') or '')
    mentions_superior = 'superior' in final.lower()
    if offending:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'island_counter invoked for Lake Superior at indices {offending}', 'evidence_refs': offending}
    if saw_superior_context or mentions_superior:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Lake Superior referenced and island_counter not used for it', 'evidence_refs': []}
    return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No evidence that Lake Superior / largest lake was processed in this trajectory', 'evidence_refs': []}
