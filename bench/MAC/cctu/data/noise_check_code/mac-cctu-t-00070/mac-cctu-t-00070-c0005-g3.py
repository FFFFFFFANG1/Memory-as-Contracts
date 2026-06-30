def evaluate(trace):
    import re
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls', 'evidence_refs': []}
    first = calls[0].get('name')
    if first != 'economic_data_retriever':
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'first tool was {first}, not economic_data_retriever', 'evidence_refs': [{'index': 0, 'name': first}]}
    resp = trace.get('final_response') or ''
    has_money = bool(re.search(r'\$|\busd\b|\bdollars?\b', resp, re.I))
    if not has_money:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'no monetary figures detected to verify USD+timestamp formatting', 'evidence_refs': []}
    usd_ok = bool(re.search(r'(USD|\$|US\$)', resp))
    ts_ok = bool(re.search(r'\b(20\d{2}|19\d{2})[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}:\d{2}|timestamp|retriev(ed|al)', resp, re.I))
    if usd_ok and ts_ok:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'economic_data_retriever called first; USD and timestamp present', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': f'usd_marker={usd_ok}, timestamp_marker={ts_ok}', 'evidence_refs': []}
