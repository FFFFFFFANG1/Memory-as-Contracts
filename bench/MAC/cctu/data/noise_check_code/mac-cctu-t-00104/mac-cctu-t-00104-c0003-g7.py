def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls', []) or []
    final = trace.get('final_response', '') or ''
    merged_calls = [t for t in tool_calls if t.get('name') == 'merged_subscriber_data_tool']
    if not merged_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'merged_subscriber_data_tool not used', 'evidence_refs': []}
    has_figures = bool(re.search(r'\d', final))
    if not has_figures:
        return {'observed_followed': True, 'confidence': 'low', 'reason': 'No numeric figures quoted in final response', 'evidence_refs': []}
    merged_indices = [t.get('index', 0) for t in merged_calls]
    first_merged = min(merged_indices) if merged_indices else 0
    other_after = [t for t in tool_calls if t.get('name') != 'merged_subscriber_data_tool' and t.get('index', 0) > first_merged]
    if not other_after:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Figures quoted but no independent tool called after merged_subscriber_data_tool to cross-check', 'evidence_refs': [str(i) for i in merged_indices]}
    return {'observed_followed': True, 'confidence': 'low', 'reason': 'Independent tool calls present after merged_subscriber_data_tool; cross-check plausible but not verifiable per-fact', 'evidence_refs': [str(i) for i in merged_indices]}
