def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    final = trace.get('final_response') or ''
    # Check 1: no parallel tool calls (one at a time)
    parallel_violation = False
    for step in traj:
        tcs = step.get('tool_calls') or []
        if len(tcs) > 1:
            parallel_violation = True
            break
    if parallel_violation:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Multiple tool calls invoked in parallel within a single step.', 'evidence_refs': []}
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls present to evaluate verbatim reproduction.', 'evidence_refs': []}
    # Check 2: raw tool outputs reproduced verbatim in final response
    missing = []
    for tc in tool_calls:
        result = tc.get('result')
        if result is None:
            continue
        rs = result if isinstance(result, str) else str(result)
        rs_stripped = rs.strip()
        if not rs_stripped:
            continue
        # try direct substring match
        if rs_stripped in final:
            continue
        # try matching a substantial chunk
        chunk = rs_stripped[:120]
        if chunk and chunk in final:
            continue
        missing.append(tc.get('name'))
    if missing:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Raw tool output(s) not reproduced verbatim in final response for: {missing}.', 'evidence_refs': []}
    # Check 3: difference mentioned after the raw output
    has_diff = bool(re.search(r'differ|difference|gap|minus|subtract|-\s*\d', final, re.I))
    if not has_diff:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'Could not confirm a calculated difference statement.', 'evidence_refs': []}
    # Verify ordering: at least one raw output appears before difference statement
    diff_match = re.search(r'differ|difference|gap', final, re.I)
    if diff_match:
        diff_pos = diff_match.start()
        ok_order = False
        for tc in tool_calls:
            result = tc.get('result')
            if result is None:
                continue
            rs = (result if isinstance(result, str) else str(result)).strip()
            if not rs:
                continue
            idx = final.find(rs[:120])
            if idx != -1 and idx < diff_pos:
                ok_order = True
                break
        if not ok_order:
            return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Difference stated before reproducing raw tool output.', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Sequential tool calls and raw outputs reproduced before difference.', 'evidence_refs': []}
