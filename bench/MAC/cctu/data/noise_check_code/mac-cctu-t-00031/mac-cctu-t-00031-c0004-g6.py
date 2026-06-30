def evaluate(trace):
    allowed = {
        'election_result_analyzer','election_result_fetcher','election_result_finder',
        'election_result_retriever','historical_event_finder','historical_weather_data_retriever',
        'legal_event_finder','papal_event_retriever','political_event_tracker',
        'political_officeholder_finder'
    }
    tool_calls = trace.get('tool_calls') or []
    names = [str(c.get('name') or '') for c in tool_calls if c.get('name')]
    if len(names) == 0:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'constraint requires obtaining answers via tool calls but no tool calls were made', 'evidence_refs': []}
    forbidden = [n for n in names if n not in allowed]
    if forbidden:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'forbidden/unlisted tools used: ' + ', '.join(sorted(set(forbidden))), 'evidence_refs': []}
    if len(names) > 10:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'tool call count ' + str(len(names)) + ' exceeds 10', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'tool calls present (' + str(len(names)) + '), all within allowed set and within 10-call budget', 'evidence_refs': []}
