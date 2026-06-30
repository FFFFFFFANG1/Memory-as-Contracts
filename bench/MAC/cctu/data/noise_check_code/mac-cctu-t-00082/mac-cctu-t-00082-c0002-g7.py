def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    tool_calls = trace.get('tool_calls') or []
    # Detect rich formatting characters
    rich_patterns = [r'```', r'\*\*', r'__', r'^#+ ', r'\|.*\|', r'^\s*[-*+] ', r'\[[^\]]+\]\([^)]+\)']
    rich_found = []
    for pat in rich_patterns:
        if re.search(pat, text, re.MULTILINE):
            rich_found.append(pat)
    lines = [l for l in text.splitlines() if l.strip()]
    # Try to find lines that look like tool invocations
    tool_names = set()
    for tc in tool_calls:
        n = tc.get('name')
        if n: tool_names.add(n)
    if not tool_names:
        return {'observed_followed': None,'confidence':'unknown','reason':'no tool calls recorded to verify transcript','evidence_refs':[]}
    invocation_lines = [l for l in lines if any(tn in l for tn in tool_names)]
    # Each tool call should appear on its own line; check no line contains multiple tool names
    multi_on_line = False
    for l in invocation_lines:
        count = sum(1 for tn in tool_names if tn in l)
        if count > 1:
            multi_on_line = True
            break
    coverage = len(invocation_lines) >= len(tool_calls) if tool_calls else False
    followed = (not rich_found) and (not multi_on_line) and coverage
    reason_parts = []
    if rich_found: reason_parts.append(f'rich formatting detected: {rich_found}')
    if multi_on_line: reason_parts.append('multiple tool invocations on one line')
    if not coverage: reason_parts.append(f'only {len(invocation_lines)} invocation lines for {len(tool_calls)} tool calls')
    if not reason_parts: reason_parts.append('plain-text transcript with one invocation per line')
    return {'observed_followed': bool(followed),'confidence':'medium','reason':'; '.join(reason_parts),'evidence_refs':[]}
