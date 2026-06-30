def evaluate(trace):
    tcs = trace.get('tool_calls') or []
    if not tcs:
        return {"observed_followed": None, "confidence": "unknown", "reason": "No tool calls found", "evidence_refs": []}
    text = ((trace.get('final_response') or '') + ' ').lower()
    traj = trace.get('trajectory') or []
    for step in traj:
        c = step.get('content') or ''
        if isinstance(c, str):
            text += ' ' + c.lower()
    mentions_catalog = any(k in text for k in ['catalog', 'catalogue', 'registry', 'list of tools', 'available tools'])
    mentions_dry_run = any(k in text for k in ['dry-run', 'dry run', 'probe', 'ping', 'health check'])
    if not (mentions_catalog or mentions_dry_run):
        return {"observed_followed": False, "confidence": "medium", "reason": "No evidence of tool registry cataloguing or dry-run probing before seismic query", "evidence_refs": []}
    return {"observed_followed": None, "confidence": "low", "reason": "Some mention of cataloguing/probing but cannot verify dry-run completion before substantive call", "evidence_refs": []}
