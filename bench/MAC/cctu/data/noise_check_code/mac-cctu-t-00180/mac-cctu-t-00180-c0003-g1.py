def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tcs = trace.get('tool_calls') or []
    if not tcs:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls in trajectory', 'evidence_refs': []}
    first_iter = min((tc.get('iteration', tc.get('index', 0)) for tc in tcs), default=None)
    pre_text = ''
    for i, step in enumerate(traj):
        has_tc = bool(step.get('tool_calls'))
        if has_tc:
            break
        pre_text += '\n' + (step.get('content') or '')
    if not pre_text.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No textual content before first tool invocation', 'evidence_refs': []}
    low = pre_text.lower()
    sub_q = bool(re.search(r'sub-?question|sub-?task|step\s*\d|decompos', low))
    tool_mention = bool(re.search(r'tool|use\s+the|invoke|call', low)) or any((t.lower() in low) for t in (trace.get('available_tools') or []))
    # also check if any actual tool name appears
    tool_names = ['advanced_arithmetic_calculator','biodiversity_database','biographical_residence_locator','climate_data_retriever','coral_reef_info_finder','historical_figure_info','historical_term_origin_finder','invention_inventor_lookup','museum_locator','museum_visitor_statistics','vineyard_region_identifier']
    tool_named = any(t in low for t in tool_names) or tool_mention
    dep = bool(re.search(r'depend|after|before|then|requires|prerequisite|first|next|finally|order', low))
    score = sum([sub_q, tool_named, dep])
    if score == 3:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'Pre-tool decomposition mentions sub-questions, tools, and dependencies', 'evidence_refs': []}
    if score >= 2:
        return {'observed_followed': True, 'confidence': 'low', 'reason': 'Partial decomposition present', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Pre-tool text lacks decomposition elements (sub-questions/tools/dependencies)', 'evidence_refs': []}
