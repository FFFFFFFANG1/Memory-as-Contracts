def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    # Count flight_status_checker calls and total calls
    fsc_count = sum(1 for c in tool_calls if (c.get('name') or '') == 'flight_status_checker')
    total_count = len(tool_calls)
    reasons = []
    # Constraint: exactly two flight_status_checker calls, and total tool invocations capped at two (i.e., only those two)
    if total_count != 2 or fsc_count != 2:
        reasons.append('tool invocation count mismatch: total=' + str(total_count) + ', flight_status_checker=' + str(fsc_count) + ' (expected exactly 2 flight_status_checker and no others)')
    # YAML format check on response for flight numbers
    if not response.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'empty response', 'evidence_refs': []}
    # Detect YAML-style list of flight numbers (e.g., lines like '- AA123' or 'flights:\n  - ...')
    yaml_list_pattern = re.compile(r'(^|\n)\s*-\s*[A-Z0-9]{2,}\s*\d+', re.IGNORECASE)
    yaml_key_pattern = re.compile(r'(^|\n)\s*[A-Za-z_][A-Za-z0-9_ ]*:\s*(\n|\s*\[)', re.MULTILINE)
    flight_num_pattern = re.compile(r'\b[A-Z]{2,3}\s*\d{1,4}\b')
    has_yaml_list = bool(yaml_list_pattern.search(response))
    has_yaml_key = bool(yaml_key_pattern.search(response))
    has_flight_numbers = bool(flight_num_pattern.search(response))
    if not has_flight_numbers:
        # No flight numbers listed; cannot confirm YAML formatting of them
        reasons.append('no flight numbers found in response')
    elif not (has_yaml_list or has_yaml_key):
        reasons.append('flight numbers not presented in YAML format (no YAML list/key structure detected)')
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'YAML-formatted flight numbers present and exactly two flight_status_checker tool calls', 'evidence_refs': []}
