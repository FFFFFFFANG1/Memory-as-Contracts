def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    # Must start with ``` and end with ```
    m = re.match(r'^```([^\s`]+)\s*\n([\s\S]*?)\n?```\s*$', resp)
    if not m:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'response is not a single fenced code block', 'evidence_refs': [resp[:120]]}
    tag = m.group(1).strip()
    if not tag:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'fenced block lacks language/endpoint tag', 'evidence_refs': [resp[:120]]}
    # Ensure nothing outside the single fence (no prose before/after)
    # Already enforced by regex anchors
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'single fenced block tagged with {tag} and no surrounding prose', 'evidence_refs': [tag]}
