def evaluate(trace):
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    # Strip trailing closing quotes/brackets to find true terminal punctuation
    tail = resp.rstrip('"\'\u201d\u2019)]}')
    if not tail:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'no terminal punctuation found', 'evidence_refs': [resp[-10:]]}
    last = tail[-1]
    if last in '.!?':
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'ends with {last!r}', 'evidence_refs': [resp[-15:]]}
    return {'observed_followed': False, 'confidence': 'high', 'reason': f'ends with {last!r}, not closing punctuation', 'evidence_refs': [resp[-15:]]}
