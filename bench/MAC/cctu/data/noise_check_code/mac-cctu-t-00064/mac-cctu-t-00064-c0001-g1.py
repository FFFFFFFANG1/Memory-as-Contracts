def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls found', 'evidence_refs': []}
    allowed = {'quarry_locator', 'mountain_quarry_locator'}
    forbidden = {'architect_material_finder', 'national_symbol_finder', 'individual_origin_identifier', 'stone_origin_locator'}
    initial = []
    for c in calls:
        name = c.get('name')
        if name in allowed:
            initial.append(c)
            continue
        break
    if not initial:
        first = calls[0].get('name')
        if first in forbidden:
            return {'observed_followed': False, 'confidence': 'high', 'reason': f'initial stage began with forbidden tool {first}', 'evidence_refs': [calls[0].get('index')]}
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'initial stage did not start with quarry tools; started with {first}', 'evidence_refs': [calls[0].get('index')]}
    violations = [c for c in initial if c.get('name') in forbidden]
    if violations:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'forbidden tool used during initial inventory stage', 'evidence_refs': [v.get('index') for v in violations]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'initial stage used only quarry_locator/mountain_quarry_locator ({len(initial)} calls) before switching tools', 'evidence_refs': [c.get('index') for c in initial]}
