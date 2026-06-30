def evaluate(trace):
    allowed = {'island_beach_finder','oasis_feature_locator'}
    calls = trace.get('tool_calls') or []
    bad = [c.get('name') for c in calls if c.get('name') and c.get('name') not in allowed]
    final = (trace.get('final_response') or '').strip()
    if not final:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    import re
    lines = final.split('\n')
    list_pat = re.compile(r'^\s*(?:[-*+•]|\d+[\.\)])\s+')
    has_list = any(list_pat.match(ln) for ln in lines)
    # single paragraph: no blank line separating text blocks
    non_empty = [ln for ln in lines if ln.strip()]
    blank_between = False
    seen_text = False
    ended = False
    for ln in lines:
        if ln.strip():
            if ended:
                blank_between = True
                break
            seen_text = True
        else:
            if seen_text:
                ended = True
    multi_para = blank_between
    reasons = []
    if bad:
        reasons.append('disallowed tools: ' + ','.join(sorted(set(bad))))
    if has_list:
        reasons.append('contains list formatting')
    if multi_para:
        reasons.append('multiple paragraphs detected')
    followed = not reasons
    return {'observed_followed': followed, 'confidence':'high' if (bad or has_list or multi_para or calls) else 'medium', 'reason': '; '.join(reasons) or 'tools restricted and single-paragraph blurb without lists', 'evidence_refs':[]}
