def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    pre_text_parts = []
    first_tool_step = None
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if tcs:
            first_tool_step = i
            if content:
                pre_text_parts.append(content)
            break
        else:
            if content:
                pre_text_parts.append(content)
    if first_tool_step is None:
        tcs_flat = trace.get('tool_calls') or []
        if not tcs_flat:
            return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls found','evidence_refs':[]}
    text = '\n'.join(pre_text_parts).lower()
    if not text.strip():
        return {'observed_followed': False, 'confidence':'high','reason':'no written content before first tool call','evidence_refs':[]}
    tool_names = ['algorithm_insight_extractor','biographical_info_finder','corporate_partnership_finder','cuisine_explorer','culinary_ingredient_identifier','geographic_feature_locator','gym_membership_pricing_tool','math_formula_origin_finder','nearby_reef_locator','quarry_mineral_locator','satellite_launch_info_retriever','software_algorithm_identifier','space_agency_locator']
    decomp_kw = ['sub-task','subtask','sub task','decompos','step 1','1.','breakdown','break down','atomic','plan']
    order_kw = ['order','sequence','then','first','next','plan','will use','will call']
    has_decomp = any(k in text for k in decomp_kw)
    has_order = any(k in text for k in order_kw)
    mentioned_tools = [t for t in tool_names if t in text]
    has_tool_list = len(mentioned_tools) >= 1
    followed = has_decomp and (has_order or has_tool_list) and has_tool_list
    if followed:
        return {'observed_followed': True, 'confidence':'medium','reason':'pre-tool text contains decomposition and planned tool order','evidence_refs':[]}
    return {'observed_followed': False, 'confidence':'medium','reason':f'missing decomposition/tool-order; decomp={has_decomp} order={has_order} tools_listed={mentioned_tools}','evidence_refs':[]}
