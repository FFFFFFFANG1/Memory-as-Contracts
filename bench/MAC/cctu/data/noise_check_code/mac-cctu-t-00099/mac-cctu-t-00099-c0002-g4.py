def evaluate(trace):
    import re
    calls = [c for c in trace.get('tool_calls', []) if c.get('name') == 'historical_event_locator']
    if not calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'historical_event_locator was not called', 'evidence_refs': []}
    phrasings = []
    for c in calls:
        args = c.get('arguments', {})
        if isinstance(args, dict):
            text = ' '.join(str(v) for v in args.values())
        else:
            text = str(args)
        text = text.strip().lower()
        if text:
            phrasings.append(text)
    distinct = set(phrasings)
    if len(distinct) < 3:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Only {len(distinct)} distinct phrasings used across historical_event_locator calls', 'evidence_refs': []}
    final = (trace.get('final_response') or '').lower()
    reconcile_hint = any(k in final for k in ['reconcil', 'discrepan', 'differ', 'conflict', 'consistent', 'cross-check', 'cross check', 'agree'])
    if not reconcile_hint:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'At least 3 distinct phrasings present, but cannot confirm reconciliation of discrepancies from final response', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'{len(distinct)} distinct phrasings used and reconciliation discussed', 'evidence_refs': []}
