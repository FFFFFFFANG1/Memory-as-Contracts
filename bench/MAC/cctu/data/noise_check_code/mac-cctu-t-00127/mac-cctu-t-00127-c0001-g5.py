def evaluate(trace):
    tool_calls = trace.get('tool_calls', []) or []
    names = [c.get('name','') for c in tool_calls]
    used_aircraft = any(n == 'aircraft_specifications_retriever' for n in names)
    used_sales = any(n == 'historical_sales_data_retriever' for n in names)
    final = (trace.get('final_response') or '')
    if not used_aircraft and 'aircraft' not in final.lower():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No aircraft specification context detected.', 'evidence_refs': []}
    if used_sales:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'historical_sales_data_retriever was invoked alongside aircraft spec context.', 'evidence_refs': [n for n in names]}
    return {'observed_followed': False, 'confidence': 'high', 'reason': 'Aircraft spec context present but historical_sales_data_retriever was not called.', 'evidence_refs': [n for n in names]}
