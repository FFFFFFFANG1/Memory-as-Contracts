def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '').strip()
    tool_calls = trace.get('tool_calls') or []
    if not response and not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no observable behavior', 'evidence_refs': []}
    # Check sports_event_winner_finder was used
    sewf_indices = [i for i, tc in enumerate(tool_calls) if (tc.get('name') or '') == 'sports_event_winner_finder']
    if not sewf_indices:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'sports_event_winner_finder not invoked', 'evidence_refs': []}
    # Try to extract CSV-like content from final response
    lines = [ln.strip() for ln in response.splitlines() if ln.strip()]
    csv_lines = [ln for ln in lines if ',' in ln and not ln.startswith('#')]
    if not csv_lines:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'no CSV-formatted content in final response', 'evidence_refs': []}
    # Identify country code column: assume first field per row is country code
    # Skip a header row if present (non-uppercase first field)
    data_rows = []
    for ln in csv_lines:
        fields = [f.strip() for f in ln.split(',')]
        if not fields or not fields[0]:
            continue
        data_rows.append(fields)
    if len(data_rows) < 2:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'insufficient CSV rows to verify ordering', 'evidence_refs': []}
    # Drop header if first row's first field is not a country-code-like token
    first = data_rows[0][0]
    if not re.fullmatch(r'[A-Za-z]{2,4}', first):
        data_rows = data_rows[1:]
    codes = [r[0] for r in data_rows if r]
    if len(codes) < 2:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'too few country code entries', 'evidence_refs': []}
    if codes != sorted(codes):
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'CSV rows not ordered by country code: {codes}', 'evidence_refs': []}
    # Verify the tool call occurred before final submission (it's by nature before final response)
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'CSV ordered by country code and sports_event_winner_finder invoked', 'evidence_refs': [{'tool_call_index': sewf_indices[0]}]}
