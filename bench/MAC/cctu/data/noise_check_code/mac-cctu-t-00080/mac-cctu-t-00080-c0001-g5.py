def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found', 'evidence_refs': []}
    names = [c.get('name') for c in calls]
    if 'rental_price_analyzer' not in names:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'rental_price_analyzer not invoked; cannot confirm analysis chain context', 'evidence_refs': []}
    last = names[-1]
    if last == 'rental_price_analyzer':
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'rental_price_analyzer is the final tool invoked', 'evidence_refs': [{'index': len(names)-1, 'name': last}]}
    return {'observed_followed': False, 'confidence': 'high', 'reason': f'Final tool was {last}, not rental_price_analyzer', 'evidence_refs': [{'index': len(names)-1, 'name': last}]}
