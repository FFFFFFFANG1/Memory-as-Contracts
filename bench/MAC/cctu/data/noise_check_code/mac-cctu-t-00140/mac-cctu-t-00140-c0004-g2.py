def evaluate(trace):
    import json
    final = (trace.get('final_response') or '').strip()
    tool_calls = trace.get('tool_calls') or []
    relevant = [tc for tc in tool_calls if tc.get('name') in ('historical_event_tool','historical_fact_retriever')]
    if not relevant:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No relevant tool calls found', 'evidence_refs': []}
    if not final:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Empty final response', 'evidence_refs': []}
    # Must parse as JSON (raw payload)
    try:
        parsed = json.loads(final)
    except Exception:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Final response is not raw JSON', 'evidence_refs': [final[:120]]}
    # Check final contains content matching tool results verbatim (no prose wrapping means it should be json only, already passed)
    # Verify final response substantially matches at least one tool result payload
    results_text = []
    for tc in relevant:
        r = tc.get('result')
        if r is None:
            continue
        if isinstance(r, (dict, list)):
            try:
                results_text.append(json.dumps(r, sort_keys=True))
            except Exception:
                results_text.append(str(r))
        else:
            results_text.append(str(r))
    try:
        final_norm = json.dumps(parsed, sort_keys=True)
    except Exception:
        final_norm = final
    matched = False
    for rt in results_text:
        try:
            rt_parsed = json.loads(rt) if isinstance(rt, str) else rt
            rt_norm = json.dumps(rt_parsed, sort_keys=True)
        except Exception:
            rt_norm = rt
        if rt_norm and (rt_norm in final_norm or final_norm in rt_norm):
            matched = True
            break
        if rt and isinstance(rt, str) and rt.strip() and rt.strip() in final:
            matched = True
            break
    if matched:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'Final response is raw JSON matching tool payload', 'evidence_refs': []}
    return {'observed_followed': None, 'confidence': 'low', 'reason': 'Final is JSON but could not confirm verbatim match with tool payloads', 'evidence_refs': []}
