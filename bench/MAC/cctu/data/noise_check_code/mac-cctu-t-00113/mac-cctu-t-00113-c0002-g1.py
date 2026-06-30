def evaluate(trace):
    history_tools = {'global_event_reach_analyzer','historical_event_finder','historical_event_info_retriever','historical_event_tool','merged_historical_event_tool'}
    calls = trace.get('tool_calls') or []
    used = [c for c in calls if c.get('name') in history_tools]
    distinct = {c.get('name') for c in used}
    if not used:
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'No historical event tool calls found; cannot determine cross-checking.', 'evidence_refs':[]}
    if len(distinct) < 2:
        return {'observed_followed': False, 'confidence':'medium', 'reason': f'Only {len(distinct)} distinct historical event tool(s) used ({sorted(distinct)}); cross-checking against >=2 distinct tools not evidenced.', 'evidence_refs':[{'tools_used': sorted(distinct)}]}
    return {'observed_followed': True, 'confidence':'low', 'reason': f'At least 2 distinct historical event tools used ({sorted(distinct)}); per-date cross-checking is plausible but not strictly verifiable from trace.', 'evidence_refs':[{'tools_used': sorted(distinct), 'count': len(used)}]}
