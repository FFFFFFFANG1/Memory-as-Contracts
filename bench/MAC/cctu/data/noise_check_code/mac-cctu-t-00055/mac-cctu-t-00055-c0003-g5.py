def evaluate(trace):
    import re
    tcs = trace.get('tool_calls') or []
    final = trace.get('final_response') or ''
    if not tcs:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found', 'evidence_refs': []}
    first = tcs[0].get('name')
    if first != 'ticket_price_checker':
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'First tool was {first}, not ticket_price_checker', 'evidence_refs': [{'first_tool': first}]}
    has_usd = bool(re.search(r'\bUSD\b|\$\s?\d', final))
    has_buffer = bool(re.search(r'12\s?%|12 percent|0\.12|buffer|seasonal', final, re.I))
    if not has_usd:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Admission costs not reported in USD', 'evidence_refs': []}
    if not has_buffer:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'No 12% seasonal buffer mentioned', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'First tool is ticket_price_checker; USD and 12% buffer mentioned', 'evidence_refs': []}
