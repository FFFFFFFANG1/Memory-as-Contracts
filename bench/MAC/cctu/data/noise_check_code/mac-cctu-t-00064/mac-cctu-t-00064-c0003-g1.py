def evaluate(trace):
    calls = trace.get('tool_calls', [])
    quarry = {'mountain_quarry_locator','quarry_locator'}
    later = {'architect_material_finder','national_symbol_finder'}
    names = [c.get('name') for c in calls]
    if not any(n in quarry for n in names) and not any(n in later for n in names):
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No relevant tools called.', 'evidence_refs': []}
    if not any(n in later for n in names):
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'No architect/cultural symbol tools invoked; ordering trivially satisfied.', 'evidence_refs': names}
    first_later = next((i for i,n in enumerate(names) if n in later), None)
    quarry_before = [i for i,n in enumerate(names) if n in quarry and i < first_later]
    if not quarry_before:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Architect/cultural tool {names[first_later]} called before any quarry locator.', 'evidence_refs': names}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'Quarry locator(s) invoked before architect/cultural symbol tools.', 'evidence_refs': names}
