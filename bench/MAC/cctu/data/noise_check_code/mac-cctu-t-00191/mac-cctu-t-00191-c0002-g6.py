def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    text = ''
    for step in traj:
        c = step.get('content') or ''
        if c:
            text = c
            break
    if not text:
        fr = trace.get('final_response') or ''
        text = fr[:2000]
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'no initial planning notes found','evidence_refs':[]}
    low = text.lower()
    # sub-questions enumerated: look for list markers or 'sub-question'
    has_subq = bool(re.search(r'sub[- ]?question|question\s*\d|q\d[:.\)]', low)) or len(re.findall(r'(^|\n)\s*(?:[-*\d]+[\.\)]|\d+\))', text)) >= 2
    # tools considered: mention of tool names or 'tool'
    tool_names = ['elevation_finder','geographical_feature_identifier','historical_event_locator','historical_geography_associator','landmark_age_retriever','philosopher_identifier','poet_identifier','political_leader_identifier']
    tool_hits = sum(1 for t in tool_names if t in low)
    has_tools = tool_hits >= 1 or 'tool' in low
    # parallelization explicitly marked
    has_parallel = bool(re.search(r'parallel|concurrent|simultaneous|in parallel', low))
    passed = has_subq and has_tools and has_parallel
    reason = f'subq={has_subq}, tools={has_tools}(hits={tool_hits}), parallel_marked={has_parallel}'
    conf = 'high' if passed else ('medium' if (has_subq or has_tools or has_parallel) else 'medium')
    return {'observed_followed': bool(passed), 'confidence': conf, 'reason': reason, 'evidence_refs': []}
