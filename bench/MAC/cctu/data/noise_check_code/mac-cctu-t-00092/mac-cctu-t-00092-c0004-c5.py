def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls') or []
    response = str(trace.get('final_response') or '').strip()
    refs = []
    if not tool_calls and not response:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no observable behavior', 'evidence_refs': []}
    # Check mineral_mine_locator is primary (first call) and used
    names = [str(tc.get('name') or '') for tc in tool_calls]
    used_mml = 'mineral_mine_locator' in names
    primary_ok = bool(names) and names[0] == 'mineral_mine_locator'
    reasons = []
    if not used_mml:
        reasons.append('mineral_mine_locator not used')
    elif not primary_ok:
        reasons.append('mineral_mine_locator not primary (first) tool; first=' + names[0])
    refs.append({'tool_sequence': names})
    # Check CSV row format: three comma-separated fields
    if not response:
        reasons.append('empty final response')
    else:
        # Find a line that looks like a CSV row of exactly 3 fields
        lines = [ln.strip() for ln in response.splitlines() if ln.strip()]
        csv_line = None
        for ln in lines:
            # ignore header-like or markdown
            parts = [p.strip().strip('"').strip("'") for p in ln.split(',')]
            if len(parts) == 3 and all(parts):
                csv_line = ln
                break
        if csv_line is None:
            reasons.append('final response is not a CSV row of 3 fields (mine, country, commodity)')
        else:
            refs.append({'csv_row': csv_line})
    if reasons:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': refs}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'mineral_mine_locator used as primary tool and final answer is a CSV row of 3 fields', 'evidence_refs': refs}
