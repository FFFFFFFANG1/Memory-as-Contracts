def evaluate(trace):
    import re
    final = trace.get('final_response') or ''
    calls = trace.get('tool_calls') or []
    # Check XML envelope
    stripped = final.strip()
    has_root = bool(re.search(r'^<beach_report\b[^>]*>.*</beach_report>\s*$', stripped, re.DOTALL))
    # Check tool order: first 3 calls must be beach_locator before any other tool
    other_before_three = False
    beach_count_before_other = 0
    for c in calls:
        name = c.get('name')
        if name == 'beach_locator':
            beach_count_before_other += 1
        else:
            if beach_count_before_other < 3:
                other_before_three = True
            break
    total_beach = sum(1 for c in calls if c.get('name') == 'beach_locator')
    if not calls and not final:
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'no evidence', 'evidence_refs':[]}
    followed = has_root and (not other_before_three) and total_beach >= 3
    reason = f'xml_root={has_root}, beach_before_other={beach_count_before_other}, other_before_three={other_before_three}, total_beach={total_beach}'
    return {'observed_followed': bool(followed), 'confidence':'high', 'reason': reason, 'evidence_refs':[]}
