def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    words = len(text.split())
    # Detect table formatting (pipe tables or grid tables)
    lines = text.splitlines()
    has_pipe_table = False
    for i,l in enumerate(lines):
        if l.count('|') >= 2 and i+1 < len(lines) and re.match(r'^\s*\|?\s*:?-{2,}', lines[i+1]):
            has_pipe_table = True
            break
    # Detect comparative content heuristically
    comp_keywords = ['compare','comparison','vs','versus','between','differ','difference','contrast','whereas','while']
    lower = text.lower()
    is_comparative = any(k in lower for k in comp_keywords)
    bullet_lines = [l for l in lines if re.match(r'^\s*[-*+]\s+', l)]
    has_bullets = len(bullet_lines) >= 2
    reasons = []
    followed = True
    if words >= 200:
        followed = False
        reasons.append(f'word count {words} >= 200')
    if has_pipe_table:
        followed = False
        reasons.append('contains tabular formatting')
    if is_comparative and not has_bullets:
        followed = False
        reasons.append('comparative content not rendered as bullet list')
    if followed:
        reason = 'within word limit, no tables' + (', bullets used for comparison' if is_comparative else '; no clear comparative content detected')
        return {'observed_followed': True, 'confidence':'medium' if is_comparative else 'low','reason':reason,'evidence_refs':[]}
    return {'observed_followed': False, 'confidence':'high','reason':'; '.join(reasons),'evidence_refs':[]}
