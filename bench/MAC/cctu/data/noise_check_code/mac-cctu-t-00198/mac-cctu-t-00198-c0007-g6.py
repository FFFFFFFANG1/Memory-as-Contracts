def evaluate(trace):
    import re
    tools = ['advanced_arithmetic_calculator','biographical_affiliation_finder','biologist_specialization_finder','ecosystem_researcher_finder','enhanced_infrastructure_locator','forest_name_search','habitat_species_associator','historical_landmark_finder','landmark_info_retriever','nearby_forest_locator','park_area_calculator','tree_age_inquiry']
    response = str(trace.get('final_response') or '')
    calls = trace.get('tool_calls') or []
    if not response.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    if len(calls) > 0:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'{len(calls)} tool invocation(s) found; none permitted at scoping stage', 'evidence_refs': [str(c.get('name','')) for c in calls]}
    text = response.lower()
    missing = [t for t in tools if t.lower() not in text]
    if missing:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'missing tools in enumeration: {missing}', 'evidence_refs': []}
    # Verify each tool has a one-line justification nearby (same line or adjacent)
    lines = response.splitlines()
    unjustified = []
    for t in tools:
        found_line = None
        for i, ln in enumerate(lines):
            if t.lower() in ln.lower():
                found_line = i
                break
        if found_line is None:
            unjustified.append(t)
            continue
        ln = lines[found_line]
        # justification = additional descriptive content on same line beyond the tool name
        stripped = re.sub(re.escape(t), '', ln, flags=re.IGNORECASE).strip(' \t-:•*—–.,()[]')
        if len(stripped.split()) < 3:
            # check next line as fallback
            nxt = lines[found_line+1].strip() if found_line+1 < len(lines) else ''
            if len(nxt.split()) < 3:
                unjustified.append(t)
    if unjustified:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'tools without one-line justification: {unjustified}', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'all tools enumerated with justifications and no invocations made', 'evidence_refs': []}
