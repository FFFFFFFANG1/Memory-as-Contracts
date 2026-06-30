def evaluate(trace):
    import re
    price_tools = {'fuel_price_checker','merged_price_checker','oil_gas_price_predictor'}
    calls = trace.get('tool_calls') or []
    used = [c for c in calls if (c.get('name') or '') in price_tools]
    if not used:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No price feed tool calls observed.', 'evidence_refs': []}
    distinct = {c.get('name') for c in used}
    cross_checked = len(distinct) >= 2
    final = (trace.get('final_response') or '').lower()
    prov_patterns = [r'source', r'endpoint', r'provenance', r'retrieved from', r'via\s+\w+', r'according to']
    has_prov = any(re.search(p, final) for p in prov_patterns)
    mentions_tool = any(t in final for t in price_tools)
    followed = cross_checked and (has_prov or mentions_tool)
    return {
        'observed_followed': bool(followed),
        'confidence': 'medium',
        'reason': f'Distinct price tools used: {sorted(distinct)}; provenance terms present: {has_prov}; tool named in final: {mentions_tool}.',
        'evidence_refs': []
    }
