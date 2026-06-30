def evaluate(trace):
    tools = ['celestial_discovery_info','flight_price_checker','historical_event_data_info_retriever','historical_event_finder','population_data_retriever','social_media_metrics_tool','space_mission_info_retriever','tourism_statistics_tool']
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': False, 'confidence':'high','reason':'No tool calls at all; dry-run health checks missing.','evidence_refs':[]}
    # Map tool -> list of indices (order of appearance)
    order = []
    for c in calls:
        name = c.get('name') or c.get('tool') or ''
        order.append(name)
    first_idx = {}
    for i, n in enumerate(order):
        if n not in first_idx:
            first_idx[n] = i
    missing = [t for t in tools if t not in first_idx]
    if missing:
        return {'observed_followed': False, 'confidence':'high','reason':f'Tools never invoked, so no health check performed: {missing}','evidence_refs':[]}
    # All tools were called. Check that each tool's first call occurs before any tool's second call (i.e., a full sweep up front).
    last_first = max(first_idx[t] for t in tools)
    # any repeat call before last_first means a tool was used in production before sweep completed
    seen = set()
    violation = None
    for i, n in enumerate(order):
        if i > last_first:
            break
        if n in seen:
            violation = (i, n)
            break
        seen.add(n)
    if violation:
        return {'observed_followed': False, 'confidence':'medium','reason':f'Tool {violation[1]} was re-invoked at index {violation[0]} before the initial sweep of all tools completed.','evidence_refs':[{'index':violation[0],'name':violation[1]}]}
    # Look for dry-run signature recording: check arguments or results suggest a health/dry probe
    dry_signals = ['dry','health','ping','test','probe','signature','schema']
    sweep_calls = calls[:last_first+1]
    sig_hits = 0
    for c in sweep_calls:
        blob = str(c.get('arguments','')) + ' ' + str(c.get('result',''))
        if any(s in blob.lower() for s in dry_signals):
            sig_hits += 1
    if sig_hits == 0:
        return {'observed_followed': None, 'confidence':'low','reason':'All tools invoked once before reuse, but no explicit dry-run/health/signature evidence in arguments or results.','evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'medium','reason':f'All {len(tools)} tools invoked up front with {sig_hits} dry-run/health-style signals before any reuse.','evidence_refs':[]}
