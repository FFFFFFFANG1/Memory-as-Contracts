def evaluate(trace):
    import re
    tools = ['award_winner_finder','chef_dish_finder','delta_port_locator','landmark_country_locator','local_cuisine_explorer','location_identifier','organization_locator','person_location_finder','port_locator','professor_identifier','seafood_origin_locator','stone_origin_locator','supplier_store_linker']
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    # Collect early assistant content before first substantive tool call
    early_text = ''
    first_tool_idx = None
    for i, step in enumerate(traj):
        tc = step.get('tool_calls') or []
        if tc:
            first_tool_idx = i
            break
        early_text += '\n' + (step.get('content') or '')
    final = trace.get('final_response') or ''
    combined = early_text + '\n' + final
    listed = [t for t in tools if t in combined]
    # Need most tools enumerated
    enumerated = len(listed) >= max(1, int(0.8*len(tools)))
    # Look for structure markers (list bullets, numbering, table) and reachability/verify language
    has_structure = bool(re.search(r'(^|\n)\s*[-*\d\.\|]', combined))
    reach_terms = re.search(r'reach|availab|verif|inventor|check', combined, re.I)
    if not enumerated:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Only {len(listed)}/{len(tools)} tools enumerated in inventory before queries.', 'evidence_refs': []}
    if not has_structure:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Tools listed but not in a structured inventory format.', 'evidence_refs': []}
    if not reach_terms:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'No reachability/verification language present.', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'Inventory of {len(listed)} tools with structure and verification language found before substantive queries.', 'evidence_refs': []}
