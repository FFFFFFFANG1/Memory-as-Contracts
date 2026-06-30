def evaluate(trace):
    import re
    final = (trace.get('final_response') or '').strip()
    if not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    # Look for scriptural citation pattern: Word(s) Chapter:Verse(-Verse)?
    pattern = re.compile(r'\b([1-3]\s+)?[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\s+\d+:\d+(?:[-\u2013]\d+)?\b')
    matches = pattern.findall(final) if False else pattern.finditer(final)
    found = [m.group(0) for m in matches]
    if not found:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no chapter:verse style citation found in final response', 'evidence_refs': [final[:200]]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'found scriptural citation(s): {found[:3]}', 'evidence_refs': found[:3]}
