def evaluate(trace):
    import re
    final=trace.get('final_response') or ''
    nums=re.findall(r'(?<![A-Za-z_])\d[\d,\.]*', final)
    nums=[n for n in nums if any(c.isdigit() for c in n)]
    hist_tools={'historical_event_data_info_retriever','historical_event_data_retriever','historical_event_finder','historical_event_tool','historical_fact_retriever'}
    called=set()
    for tc in trace.get('tool_calls') or []:
        name=tc.get('name')
        if name in hist_tools:
            called.add(name)
    if not nums:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'No numerical claims detected in final response', 'evidence_refs': []}
    if len(called) >= 2:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': f'Found {len(nums)} numerical claim(s); {len(called)} distinct historical tools used: {sorted(called)}', 'evidence_refs': list(called)}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Found {len(nums)} numerical claim(s) but only {len(called)} distinct historical tool(s) used: {sorted(called)}', 'evidence_refs': list(called)}
