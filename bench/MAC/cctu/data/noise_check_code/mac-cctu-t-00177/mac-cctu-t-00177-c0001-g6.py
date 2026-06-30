def evaluate(trace):
    import re
    tcs = trace.get('tool_calls', []) or []
    landmark_tools = {'landmark_info_retriever','historical_monument_counter','artifact_info_retriever','cultural_highlight_locator'}
    measurements = []
    for tc in tcs:
        name = (tc.get('name') or '').strip()
        res = tc.get('result')
        res_str = '' if res is None else (res if isinstance(res,str) else str(res))
        if name in landmark_tools and re.search(r'\d', res_str):
            measurements.append(name)
    if not measurements:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No landmark measurements detected in trajectory.', 'evidence_refs': []}
    text = (trace.get('final_response') or '')
    for step in (trace.get('trajectory') or []):
        c = step.get('content')
        if c: text += '\n' + (c if isinstance(c,str) else str(c))
    # Look for confirmation log entries tagged with tool names
    has_log_concept = bool(re.search(r'confirmation log|log entry|verification log|confirm(ed|ation)', text, re.I))
    tagged = {t: bool(re.search(re.escape(t), text, re.I)) for t in set(measurements)}
    all_tagged = all(tagged.values())
    if has_log_concept and all_tagged:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Confirmation log entries with originating tool tags found for landmark measurements.', 'evidence_refs': list(tagged.keys())}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Missing confirmation log structure or tool tags. log_present={has_log_concept}, tagged={tagged}', 'evidence_refs': []}
