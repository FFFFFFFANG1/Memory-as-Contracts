def evaluate(trace):
    resp = (trace.get('final_response') or '').strip()
    tool_calls = trace.get('tool_calls') or []
    if not resp:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response', 'evidence_refs': []}
    ends_q = resp.endswith('?')
    has_mph = 'mph' in resp.lower()
    weather_count = sum(1 for tc in tool_calls if (tc.get('name') or '') == 'historical_weather_data_retriever')
    enough_weather = weather_count >= 2
    followed = ends_q and has_mph and enough_weather
    reason = f"ends_with_question={ends_q}, contains_mph={has_mph}, historical_weather_calls={weather_count}"
    return {'observed_followed': bool(followed), 'confidence': 'high', 'reason': reason, 'evidence_refs': []}
