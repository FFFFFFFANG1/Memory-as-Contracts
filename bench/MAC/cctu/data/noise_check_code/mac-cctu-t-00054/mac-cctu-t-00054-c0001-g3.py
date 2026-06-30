def evaluate(trace):
    calls = trace.get('tool_calls', []) or []
    arch = {'architect_material_locator','architectural_work_locator'}
    geo = 'geological_formation_comparator'
    first_arch_idx = None
    first_geo_idx = None
    for i, c in enumerate(calls):
        name = c.get('name')
        if name in arch and first_arch_idx is None:
            first_arch_idx = i
        if name == geo and first_geo_idx is None:
            first_geo_idx = i
    if first_arch_idx is None:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No architectural lookup tool was invoked; precedence requirement not triggered.', 'evidence_refs': []}
    if first_geo_idx is not None and first_geo_idx < first_arch_idx:
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'geological_formation_comparator at index {first_geo_idx} precedes first architectural tool at index {first_arch_idx}.', 'evidence_refs': [first_geo_idx, first_arch_idx]}
    return {'observed_followed': False, 'confidence': 'high', 'reason': 'Architectural lookup tool invoked without prior geological_formation_comparator call.', 'evidence_refs': [first_arch_idx]}
