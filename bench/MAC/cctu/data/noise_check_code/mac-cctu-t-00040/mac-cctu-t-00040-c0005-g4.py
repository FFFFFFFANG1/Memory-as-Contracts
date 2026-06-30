def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls') or []
    used_tool = any((tc.get('name')=='sports_event_result_finder') for tc in tool_calls)
    final = trace.get('final_response') or ''
    # Detect markdown table: lines with | and a separator row like |---|
    lines = final.splitlines()
    has_table = False
    for i,l in enumerate(lines):
        if '|' in l and i+1 < len(lines):
            sep = lines[i+1]
            if re.search(r'\|\s*:?-{3,}', sep):
                has_table = True
                break
    # Detect flag emoji (regional indicator pairs U+1F1E6-U+1F1FF)
    has_flag = bool(re.search(r'[\U0001F1E6-\U0001F1FF]{2}', final))
    followed = used_tool and has_table and has_flag
    reason = f'used_tool={used_tool}, markdown_table={has_table}, flag_emoji={has_flag}'
    return {'observed_followed': bool(followed), 'confidence': 'high' if (used_tool and (has_table or has_flag)) else 'medium', 'reason': reason, 'evidence_refs': []}
