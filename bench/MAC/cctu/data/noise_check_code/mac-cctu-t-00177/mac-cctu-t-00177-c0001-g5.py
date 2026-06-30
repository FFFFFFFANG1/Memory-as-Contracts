def evaluate(trace):
    import re
    calls = trace.get('tool_calls', []) or []
    used = [c for c in calls if c.get('name') in ('literary_author_finder','cultural_highlight_locator')]
    if not used:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'Neither relevant tool was invoked.', 'evidence_refs': []}
    chl_calls = [c for c in used if c.get('name') == 'cultural_highlight_locator']
    if not chl_calls:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'literary_author_finder used; cultural_highlight_locator not invoked.', 'evidence_refs': [c.get('index') for c in used]}
    lit_pattern = re.compile(r'author|writer|novelist|poet|playwright|biograph|born|birthplace|literary|book|novel|wrote|literature', re.I)
    suspicious = []
    for c in chl_calls:
        args = c.get('arguments') or {}
        result = c.get('result') or ''
        blob = ' '.join([str(v) for v in (args.values() if isinstance(args, dict) else [args])]) + ' ' + str(result)
        if lit_pattern.search(blob):
            suspicious.append(c.get('index'))
    if suspicious:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'cultural_highlight_locator appears used for literary-biography content at indices {suspicious}.', 'evidence_refs': suspicious}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'cultural_highlight_locator usage does not appear to overlap with literary-biography scope.', 'evidence_refs': [c.get('index') for c in chl_calls]}
