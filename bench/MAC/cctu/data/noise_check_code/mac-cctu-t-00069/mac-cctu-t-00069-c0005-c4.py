def evaluate(trace):
    import re
    tcs = trace.get('tool_calls') or []
    final = trace.get('final_response') or ''
    if not tcs:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found', 'evidence_refs': []}
    names = [tc.get('name') for tc in tcs]
    first_ok = names[0] == 'artist_artwork_identifier'
    last_ok = names[-1] == 'event_host_locator'
    lines = [l.strip() for l in final.splitlines() if l.strip()]
    numbered = [l for l in lines if re.match(r'^\d+[\.)\-:]\s+', l)]
    list_ok = len(numbered) >= 2
    followed = first_ok and last_ok and list_ok
    return {
        'observed_followed': bool(followed),
        'confidence': 'high' if (first_ok and last_ok) else 'medium',
        'reason': f'first={names[0]} last={names[-1]} numbered_items={len(numbered)}',
        'evidence_refs': []
    }
