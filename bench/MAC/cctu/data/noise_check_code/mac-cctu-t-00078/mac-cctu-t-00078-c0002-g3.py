def evaluate(trace):
    trace = trace or {}
    final = str(trace.get('final_response') or '').strip()
    tool_calls = trace.get('tool_calls') or []
    named = ['cultural_insight_provider','ingredient_identifier','scientific_discovery_finder','product_information_retriever','sports_sponsorship_finder','gene_trait_identifier','biographical_info_finder']
    failures = []
    evidence = []
    total = len(tool_calls)
    evidence.append({'total_tool_calls': total})
    if total > 10:
        failures.append('total tool calls ' + str(total) + ' exceeds 10')
    counts = {}
    for call in tool_calls:
        name = str((call or {}).get('name') or '')
        counts[name] = counts.get(name, 0) + 1
    evidence.append({'per_tool_counts': counts})
    for tool in named:
        c = counts.get(tool, 0)
        if c > 1:
            failures.append(tool + ' called ' + str(c) + ' times (max 1)')
    if total == 0 and final:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'final response present but no tool calls; answer cannot be derived from tool outputs', 'evidence_refs': evidence}
    if total == 0 and not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls and no final response', 'evidence_refs': evidence}
    if failures:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(failures[:8]), 'evidence_refs': evidence}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'tool call count within 10 and named tools used at most once each', 'evidence_refs': evidence}
