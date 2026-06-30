def evaluate(trace):
    import re
    final = (trace.get('final_response') or '').strip()
    calls = trace.get('tool_calls') or []
    other_tools = {
        'diplomatic_event_finder','earthquake_data_retriever','event_data_retriever',
        'event_locator','historical_event_data_retriever','historical_event_finder',
        'historical_event_lookup','political_event_finder'
    }
    prefix = 'The successor took office on'
    # Format check
    starts_ok = final.startswith(prefix)
    # Order check
    psf_first_idx = None
    other_first_idx = None
    for c in calls:
        name = c.get('name') or c.get('tool_name')
        idx = c.get('index')
        if idx is None:
            idx = calls.index(c)
        if name == 'political_successor_finder' and psf_first_idx is None:
            psf_first_idx = idx
        elif name in other_tools and other_first_idx is None:
            other_first_idx = idx
    if not calls:
        order_ok = None
        order_reason = 'no tool calls observed'
    elif other_first_idx is None:
        order_ok = True
        order_reason = 'no other historical-event tools used'
    elif psf_first_idx is None:
        order_ok = False
        order_reason = 'other historical-event tool used without political_successor_finder'
    else:
        order_ok = psf_first_idx < other_first_idx
        order_reason = f'psf idx={psf_first_idx}, other idx={other_first_idx}'
    if not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    if order_ok is None:
        followed = starts_ok if starts_ok else False
        conf = 'low'
        reason = f'prefix_ok={starts_ok}; {order_reason}'
        return {'observed_followed': followed if starts_ok else False, 'confidence': conf, 'reason': reason, 'evidence_refs': []}
    followed = bool(starts_ok and order_ok)
    return {'observed_followed': followed, 'confidence': 'high', 'reason': f'prefix_ok={starts_ok}; {order_reason}', 'evidence_refs': []}
