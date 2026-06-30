def evaluate(trace):
    import re
    tools = ['art_auction_price_finder','artifact_auction_tracker','astronomical_historian','biographical_info_retriever','city_industry_locator','historian_finder','historical_affiliation_finder','historical_location_associator','theater_finder','venue_info_retriever']
    traj = trace.get('trajectory') or []
    scratch_before = ''
    first_call_step = None
    for i, step in enumerate(traj):
        calls = step.get('tool_calls') or []
        content = step.get('content') or ''
        if calls:
            first_call_step = i
            break
        scratch_before += '\n' + str(content)
    if first_call_step is None:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found in trajectory', 'evidence_refs': []}
    text = scratch_before.lower()
    missing = [t for t in tools if t.lower() not in text]
    if missing:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Scratchpad before first tool call missing tools: {missing}', 'evidence_refs': [{'step_index': first_call_step}]}
    first_call_names = [c.get('name') for c in (traj[first_call_step].get('tool_calls') or [])]
    if 'art_auction_price_finder' in first_call_names:
        # Allowed only if inventory complete, which it is here; but constraint says refrain until inventory complete - inventory is complete pre-call, so OK
        pass
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'All tool names listed in scratchpad before any tool call', 'evidence_refs': [{'step_index': first_call_step}]}
