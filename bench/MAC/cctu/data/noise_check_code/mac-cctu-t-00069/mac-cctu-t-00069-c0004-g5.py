def evaluate(trace):
    import re
    calls = trace.get('tool_calls') or []
    cultural_tools = {'regional_cuisine_identifier','artist_artwork_identifier','historical_figure_locator','historical_company_finder','oasis_feature_locator','island_beach_finder'}
    host_idx = None
    cultural_idx = None
    for c in calls:
        name = c.get('name')
        idx = c.get('index', 0)
        if name == 'event_host_locator' and host_idx is None:
            host_idx = idx
        if name in cultural_tools and cultural_idx is None:
            cultural_idx = idx
    final = trace.get('final_response') or ''
    if not final.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    # Check bold at top
    lines = [l for l in final.splitlines() if l.strip()]
    top = lines[0] if lines else ''
    bold_match = re.search(r'\*\*([^*]+)\*\*', top)
    bold_ok = bold_match is not None
    # Order check
    if host_idx is None:
        order_ok = False
        order_reason = 'event_host_locator not called'
    elif cultural_idx is not None and cultural_idx < host_idx:
        order_ok = False
        order_reason = 'cultural/cuisine tool called before event_host_locator'
    else:
        order_ok = True
        order_reason = 'order ok'
    followed = bool(order_ok and bold_ok)
    reason = order_reason + '; ' + ('bold at top present' if bold_ok else 'no bold city at top of response')
    return {'observed_followed': followed, 'confidence': 'high', 'reason': reason, 'evidence_refs': []}
