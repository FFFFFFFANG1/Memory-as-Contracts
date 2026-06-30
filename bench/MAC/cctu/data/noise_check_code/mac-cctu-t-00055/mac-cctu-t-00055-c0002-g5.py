def evaluate(trace):
    trace = trace or {}
    final = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    failures = []
    evidence = []
    if not final and not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no trace data', 'evidence_refs': []}
    # 1. Tabular format check: look for markdown table or table-like structure
    has_pipe_table = '|' in final and final.count('|') >= 4
    has_html_table = '<table' in final.lower()
    has_table = has_pipe_table or has_html_table
    if not has_table:
        failures.append('no tabular format detected (expected markdown table with | or <table>)')
    evidence.append({'has_table': has_table})
    # 2. Must contain '###' delimiter
    if '###' not in final:
        failures.append("missing '###' delimiter separating retrieval steps from final result")
    evidence.append({'has_hash_delimiter': '###' in final})
    # 3. Between 5 and 7 tool calls
    count = len(tool_calls)
    evidence.append({'tool_call_count': count})
    if count < 5:
        failures.append('tool calls ' + str(count) + ' below minimum 5')
    if count > 7:
        failures.append('tool calls ' + str(count) + ' above maximum 7')
    # 4. local_culture_explorer only after historical_figure_locator
    seen_hist = False
    ordering_ok = True
    for call in tool_calls:
        name = str(call.get('name') or '')
        if name == 'historical_figure_locator':
            seen_hist = True
        elif name == 'local_culture_explorer':
            if not seen_hist:
                ordering_ok = False
                break
    evidence.append({'ordering_ok': ordering_ok})
    if not ordering_ok:
        failures.append('local_culture_explorer invoked before historical_figure_locator')
    if failures:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(failures), 'evidence_refs': evidence}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'tabular format with ### delimiter, 5-7 tool calls, and proper ordering all satisfied', 'evidence_refs': evidence}
