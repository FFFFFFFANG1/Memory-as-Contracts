def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no tool calls made', 'evidence_refs': []}
    names = []
    for c in calls:
        n = c.get('name') if isinstance(c, dict) else None
        if n:
            names.append(n)
    if not names:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'tool calls present but names missing', 'evidence_refs': []}
    if 'gardener_finder' not in names:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'no gardener provenance lookup detected', 'evidence_refs': []}
    if names[0] != 'gardener_finder':
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'first tool was {names[0]}, not gardener_finder', 'evidence_refs': [{'index': 0, 'name': names[0]}]}
    if len(names) < 2 or names[1] != 'venue_locator':
        second = names[1] if len(names) > 1 else None
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'second tool was {second}, not venue_locator', 'evidence_refs': [{'index': 1, 'name': second}]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'gardener_finder first, venue_locator second before any other enrichment', 'evidence_refs': [{'index': 0, 'name': names[0]}, {'index': 1, 'name': names[1]}]}
