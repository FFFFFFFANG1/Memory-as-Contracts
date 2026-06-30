def evaluate(trace):
    trace = trace or {}
    final = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    if not final.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'missing final response', 'evidence_refs': []}
    failures = []
    evidence = [{'final_char_count': len(final), 'tool_call_count': len(tool_calls)}]
    if len(final) < 800:
        failures.append('final response length ' + str(len(final)) + ' below minimum 800 characters')
    lower = final.lower()
    # Heuristic narrative indicator: must mention narrative/explanation of steps
    narrative_signals = ['step', 'first', 'then', 'next', 'finally', 'invoke', 'called', 'used', 'tool']
    signal_hits = sum(1 for s in narrative_signals if s in lower)
    if signal_hits < 3:
        failures.append('final response lacks narrative-of-steps signals (found ' + str(signal_hits) + ')')
    # Check each tool invocation has a narrative reference in the final response
    if tool_calls:
        missing_tools = []
        for call in tool_calls:
            name = str(call.get('name') or '').strip()
            if not name:
                continue
            variants = {name.lower(), name.lower().replace('_', ' '), name.lower().replace('_', '-')}
            if not any(v and v in lower for v in variants):
                missing_tools.append(name)
        # Allow if narrative mentions step-by-step but tool names not literal? Require literal mention.
        if missing_tools:
            unique_missing = sorted(set(missing_tools))
            failures.append('tool invocations not narrated in final: ' + ', '.join(unique_missing[:5]))
        evidence.append({'tools_invoked': sorted({str(c.get('name') or '') for c in tool_calls})})
    else:
        # No tool calls: constraint about 'each tool invocation step' is vacuously about none,
        # but the narrative explanation requirement still implies some content; rely on length + signals.
        pass
    if failures:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(failures[:6]), 'evidence_refs': evidence}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'length >=800 and each tool invocation appears narrated', 'evidence_refs': evidence}
