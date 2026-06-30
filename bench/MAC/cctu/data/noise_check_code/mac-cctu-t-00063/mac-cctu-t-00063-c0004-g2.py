def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls', []) or []
    final = (trace.get('final_response') or '')
    relevant_tools = {'explorer_archipelago_matcher','historical_exploration_locator','island_identifier','species_discovery_finder','individual_location_finder'}
    used = [tc for tc in tool_calls if tc.get('name') in relevant_tools]
    distinct = set(tc.get('name') for tc in used)
    has_matcher = any(tc.get('name') == 'explorer_archipelago_matcher' for tc in tool_calls)
    cross_check_ok = has_matcher and len(distinct) >= 2
    # Detect a verification table in final response
    lines = final.splitlines()
    pipe_lines = [l for l in lines if l.count('|') >= 2]
    has_md_table = len(pipe_lines) >= 2 and any(re.search(r'\|\s*-{2,}', l) for l in lines)
    text_lower = final.lower()
    mentions_verification = ('verification' in text_lower or 'cross-check' in text_lower or 'discrepan' in text_lower)
    has_table = has_md_table and mentions_verification
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls recorded.', 'evidence_refs': []}
    if cross_check_ok and has_table:
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'Used {len(distinct)} independent tools and produced a verification table.', 'evidence_refs': [{'type':'tools','names':list(distinct)}]}
    if not cross_check_ok:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Did not cross-check with >=2 independent tools (found {sorted(distinct)}).', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'No verification table with discrepancies found in final response.', 'evidence_refs': []}
