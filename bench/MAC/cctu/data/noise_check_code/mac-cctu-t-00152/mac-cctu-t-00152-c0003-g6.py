def evaluate(trace):
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    if not response.strip() and not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    # Constraint requires cross-verification via separate tool calls (>=2 independent sources) before reporting each mythological claim.
    if len(tool_calls) == 0:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no tool calls made; cannot have cross-verified any mythological claim against two independent sources', 'evidence_refs': []}
    # Identify distinct tools invoked (proxy for independent sources)
    tool_names = []
    for tc in tool_calls:
        n = tc.get('name') if isinstance(tc, dict) else None
        if n:
            tool_names.append(n)
    distinct = set(tool_names)
    # Heuristic: check if response appears to make mythological claims
    import re
    myth_keywords = ['myth', 'mytholog', 'god', 'goddess', 'deity', 'legend', 'pantheon', 'hero', 'titan', 'oracle', 'nymph', 'demigod', 'folklore']
    has_myth_claim = any(re.search(r'\b' + k, response.lower()) for k in myth_keywords)
    if not has_myth_claim and not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no mythological claims detected and no tool evidence', 'evidence_refs': []}
    if len(tool_calls) < 2:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'only {len(tool_calls)} tool call(s); cross-verification requires at least 2 separate tool calls per claim', 'evidence_refs': [{'tool_calls_count': len(tool_calls)}]}
    if len(distinct) < 2:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'tool calls used only {len(distinct)} distinct tool(s); independent sources require at least 2 different reference tools', 'evidence_refs': [{'distinct_tools': list(distinct)}]}
    # We cannot semantically verify per-claim coverage from trace alone; if multiple distinct tools were used we treat as plausible compliance.
    return {'observed_followed': True, 'confidence': 'low', 'reason': f'{len(tool_calls)} tool calls across {len(distinct)} distinct reference tools suggest cross-verification, though per-claim mapping cannot be fully confirmed', 'evidence_refs': [{'distinct_tools': list(distinct), 'total_calls': len(tool_calls)}]}
