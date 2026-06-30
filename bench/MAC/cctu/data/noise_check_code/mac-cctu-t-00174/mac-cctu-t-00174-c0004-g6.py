def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '')
    if not resp.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    low = resp.lower()
    # Check for doubles/mixed exclusion - if mentioned as included, fail
    mentions_doubles = 'doubles' in low or 'mixed' in low
    # Look for indication singles-only
    singles_focus = 'singles' in low
    # Extract a ranking: lines with numbers or ordering
    lines = [l.strip() for l in resp.splitlines() if l.strip()]
    ranked = []
    for l in lines:
        m = re.match(r'^[\(\[]?\s*(\d+)[\.\)\]:\-\s]+(.+)', l)
        if m:
            ranked.append((int(m.group(1)), m.group(2)))
    # Parse country and count from each ranked line
    import re as _re
    entries = []
    for rank, text in ranked:
        nm = _re.match(r'([A-Za-z\.\s&/-]+?)\s*[\-:\u2013\u2014\(]\s*(\d+)', text)
        if nm:
            entries.append((rank, nm.group(1).strip(), int(nm.group(2))))
    # Verify descending by count
    desc_ok = True
    for i in range(1, len(entries)):
        if entries[i][2] > entries[i-1][2]:
            desc_ok = False
            break
    # Verify ties alphabetical
    tie_ok = True
    for i in range(1, len(entries)):
        if entries[i][2] == entries[i-1][2]:
            if entries[i][1].lower() < entries[i-1][1].lower():
                tie_ok = False
                break
    if not entries:
        if singles_focus and not mentions_doubles:
            return {'observed_followed': None,'confidence':'low','reason':'no clear ranking parsed','evidence_refs':[]}
        return {'observed_followed': None,'confidence':'unknown','reason':'no ranking detected','evidence_refs':[]}
    if mentions_doubles and 'exclud' not in low and 'only singles' not in low and 'singles only' not in low:
        return {'observed_followed': False,'confidence':'low','reason':'doubles/mixed referenced without exclusion','evidence_refs':[]}
    if desc_ok and tie_ok:
        return {'observed_followed': True,'confidence':'medium','reason':'ranking descending and ties alphabetical','evidence_refs':[str(e) for e in entries]}
    return {'observed_followed': False,'confidence':'medium','reason':f'desc_ok={desc_ok} tie_ok={tie_ok}','evidence_refs':[str(e) for e in entries]}
