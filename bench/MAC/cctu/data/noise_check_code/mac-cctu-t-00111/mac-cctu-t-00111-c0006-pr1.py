def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls', []) or []
    final = (trace.get('final_response') or '')
    distance_tools = ['unified_distance_calculator']
    other_distance_hints = ['distance']
    udc_count = sum(1 for c in tool_calls if c.get('name') == 'unified_distance_calculator')
    other_count = sum(1 for c in tool_calls if c.get('name') != 'unified_distance_calculator')
    mentions_distance = bool(re.search(r'distance|miles|kilometers|km\b|nautical', final, re.I))
    if udc_count == 0 and not mentions_distance:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No distance-related activity detected.', 'evidence_refs': []}
    primarily_udc = udc_count >= 1 and udc_count >= other_count
    nm_pattern = re.search(r'nautical\s*miles?|\bnm\b|\bnmi\b', final, re.I)
    non_nm_units = re.search(r'\b(kilomet(re|er)s?|km)\b|\bstatute\s*miles?\b', final, re.I)
    has_distance_report = bool(re.search(r'\bdistance|\bapart|\bfrom\b.*\bto\b', final, re.I)) or bool(nm_pattern)
    if not has_distance_report and udc_count == 0:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No spatial relationships reported and tool not used.', 'evidence_refs': []}
    followed = primarily_udc and (nm_pattern is not None) and (non_nm_units is None)
    reason = f'udc_calls={udc_count}, other_calls={other_count}, nm_in_final={bool(nm_pattern)}, non_nm_units={bool(non_nm_units)}'
    return {'observed_followed': bool(followed), 'confidence': 'medium', 'reason': reason, 'evidence_refs': []}
