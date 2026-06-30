def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    final = trace.get('final_response') or ''
    retrieval_tools = {'constitutional_info_retriever','political_union_info','historical_event_and_fact_retriever','historical_event_facts','historical_event_tool','astronomical_discovery_info','historical_crime_analyzer','unified_population_data_retriever'}
    paired = {'constitutional_info_retriever','political_union_info'}
    turns_checked = 0
    violations = []
    for i, step in enumerate(traj):
        calls = step.get('tool_calls') or []
        names = [c.get('name') or c.get('tool_name') for c in calls]
        names = [n for n in names if n]
        if not names:
            continue
        if any(n in retrieval_tools for n in names):
            turns_checked += 1
            if not paired.issubset(set(names)):
                violations.append({'turn_index': i, 'tools': names})
    if turns_checked == 0:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No retrieval turns observed.', 'evidence_refs': []}
    founding_terms = ['Constitution','Declaration of Independence','Articles of Confederation','Bill of Rights','Magna Carta','Federalist','Treaty of','Mayflower Compact','Maastricht','Treaty of Rome','Schuman','Lisbon Treaty']
    text = final
    hits = []
    for t in founding_terms:
        if re.search(re.escape(t), text, re.IGNORECASE):
            hits.append(t)
    enough_docs = len(set(hits)) >= 2
    followed = (not violations) and enough_docs
    reason_parts = []
    if violations:
        reason_parts.append(f'{len(violations)} retrieval turn(s) lacked the required joint invocation.')
    else:
        reason_parts.append(f'All {turns_checked} retrieval turn(s) invoked the required pair jointly.')
    reason_parts.append(f'Founding-document citations detected: {hits}.')
    return {'observed_followed': bool(followed), 'confidence': 'high' if (violations or enough_docs or len(hits)==0) else 'medium', 'reason': ' '.join(reason_parts), 'evidence_refs': []}
