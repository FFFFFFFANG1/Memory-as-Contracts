def evaluate(trace):
    tool_calls = trace.get('tool_calls', []) or []
    mountain_calls = [c for c in tool_calls if c.get('name') == 'nearby_mountain_range_locator']
    country_calls = [c for c in tool_calls if c.get('name') == 'country_feature_locator']
    if not mountain_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'nearby_mountain_range_locator was never invoked', 'evidence_refs': []}
    if not country_calls:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'country_feature_locator not invoked, so no cross-check possible', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'low', 'reason': 'Both tools were invoked; per-catalog-entry coverage cannot be verified from trace alone', 'evidence_refs': [c.get('index') for c in mountain_calls + country_calls]}
