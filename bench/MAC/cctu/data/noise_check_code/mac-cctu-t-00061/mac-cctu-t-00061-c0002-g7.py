def evaluate(trace):
    trace = trace or {}
    final = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    evidence = []
    failures = []

    ssl_calls = [c for c in tool_calls if str(c.get('name') or '') == 'supplier_store_linker']
    org_calls = [c for c in tool_calls if str(c.get('name') or '') == 'organization_locator']
    evidence.append({'supplier_store_linker_count': len(ssl_calls), 'organization_locator_count': len(org_calls)})

    if not ssl_calls and not org_calls and not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls and no final response', 'evidence_refs': evidence}

    if not ssl_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no supplier_store_linker calls observed; pairing rule not triggered', 'evidence_refs': evidence}

    # Pairing: at least one organization_locator per supplier_store_linker call
    if len(org_calls) < len(ssl_calls):
        failures.append(f'supplier_store_linker calls ({len(ssl_calls)}) not paired with enough organization_locator calls ({len(org_calls)})')

    # CSV table check in final response
    import re
    has_csv_keyword = 'csv' in final.lower()
    # Detect CSV-like structure: at least two lines with commas and consistent separators
    lines = [ln for ln in final.splitlines() if ln.strip()]
    comma_lines = [ln for ln in lines if ',' in ln]
    csv_like = len(comma_lines) >= 2
    if not (has_csv_keyword or csv_like):
        failures.append('final response does not appear to contain a CSV table')
    else:
        evidence.append({'csv_keyword': has_csv_keyword, 'comma_line_count': len(comma_lines)})

    # Single CSV table - check there is not multiple disjoint csv blocks (heuristic: not enforced strictly)

    if failures:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(failures), 'evidence_refs': evidence}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'supplier_store_linker calls paired with organization_locator and CSV table present', 'evidence_refs': evidence}
