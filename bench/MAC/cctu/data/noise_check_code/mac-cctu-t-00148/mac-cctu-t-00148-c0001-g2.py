def evaluate(trace):
    import re
    final = trace.get('final_response','') or ''
    tool_calls = trace.get('tool_calls',[]) or []
    date_tool_names = {'historical_event_date_finder','historical_event_date_tool','historical_event_data_info_retriever','time_tracker'}
    date_calls = [tc for tc in tool_calls if tc.get('name') in date_tool_names]
    # Check sequential: no two date calls share the same iteration/step
    parallel_violation = False
    seen = {}
    for tc in date_calls:
        it = tc.get('iteration')
        if it is None:
            continue
        if it in seen:
            parallel_violation = True
            break
        seen[it] = True
    # Check bulleted list vs table
    has_table = bool(re.search(r'^\s*\|.*\|', final, re.MULTILINE)) or bool(re.search(r'\|[-:\s|]+\|', final))
    bullet_lines = re.findall(r'^\s*([-*•]|\d+\.)\s+\S', final, re.MULTILINE)
    has_bullets = len(bullet_lines) >= 2
    if not date_calls and not final:
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'No date calls or final response found', 'evidence_refs':[]}
    reasons = []
    ok = True
    if parallel_violation:
        ok = False
        reasons.append('Date tool calls executed in parallel (same iteration)')
    else:
        reasons.append(f'{len(date_calls)} date calls appear sequential')
    if has_table:
        ok = False
        reasons.append('Final response contains a table')
    if not has_bullets and final.strip():
        ok = False
        reasons.append('Final response is not a bulleted list')
    else:
        reasons.append(f'Found {len(bullet_lines)} bullet items')
    return {'observed_followed': ok, 'confidence': 'high' if (date_calls and final) else 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
