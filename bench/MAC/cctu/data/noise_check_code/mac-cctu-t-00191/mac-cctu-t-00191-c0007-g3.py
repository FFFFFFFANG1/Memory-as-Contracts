def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls to evaluate.', 'evidence_refs': []}
    url_re = re.compile(r'https?://\S+')
    log_kw = re.compile(r'(verification log|side[- ]channel|archive|archived|logged|log entry|citation)', re.I)
    # Collect assistant content after each tool call
    contents = []
    for step in traj:
        c = step.get('content') or ''
        if c:
            contents.append(c)
    final = trace.get('final_response') or ''
    all_text = '\n'.join(contents) + '\n' + final
    has_log_mention = bool(log_kw.search(all_text))
    has_urls = len(url_re.findall(all_text))
    tool_names_mentioned = sum(1 for tc in tool_calls if (tc.get('name') or '') in all_text)
    # Need archive evidence per tool call with tool name + URL
    if not has_log_mention:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No side-channel verification log mentioned in trajectory.', 'evidence_refs': []}
    if has_urls < len(tool_calls) or tool_names_mentioned < len(tool_calls):
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Log mention found but missing per-call tool names ({tool_names_mentioned}/{len(tool_calls)}) or citation URLs ({has_urls}/{len(tool_calls)}).', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'low', 'reason': 'Trajectory references a verification log with tool names and URLs for each call.', 'evidence_refs': []}
