def evaluate(trace):
    import re
    final = (trace.get('final_response') or '').strip()
    if not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    tool_calls = trace.get('tool_calls') or []
    used_weather = any((tc.get('name') or '') == 'weather_data_retriever' for tc in tool_calls)
    if not used_weather:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'weather_data_retriever was not called', 'evidence_refs': []}
    words = re.findall(r'\S+', final)
    wc = len(words)
    if wc > 200:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'response is {wc} words, exceeds 200', 'evidence_refs': []}
    # Inspect lead (first ~2 lines or first sentence) for a temperature anomaly figure
    lead = final.split('\n\n')[0]
    first_chunk = lead[:300]
    # Look for a numeric figure with anomaly/temperature context near the start
    has_number = bool(re.search(r'[-+\u2212]?\d+(?:\.\d+)?\s*(?:\u00b0|deg|\u2103|\u2109|C\b|F\b)', first_chunk, re.IGNORECASE))
    mentions_anomaly = bool(re.search(r'anomal', first_chunk, re.IGNORECASE))
    if not (has_number and mentions_anomaly):
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'lead does not appear to feature a temperature anomaly figure', 'evidence_refs': [first_chunk[:160]]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'{wc} words; lead contains anomaly figure; weather tool used', 'evidence_refs': [first_chunk[:160]]}
