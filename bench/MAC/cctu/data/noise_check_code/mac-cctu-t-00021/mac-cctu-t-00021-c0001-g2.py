def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    lines = [l for l in text.splitlines() if l.strip()]
    # Detect markdown/ascii table
    table_lines = [l for l in lines if l.count('|') >= 2]
    has_table = len(table_lines) >= 2 and any(re.search(r'^\s*\|?\s*:?-{2,}', l) for l in table_lines)
    # Detect numbered list items like '1.' or '1)'
    numbered = [l for l in lines if re.match(r'^\s*\d+[\.)]\s+\S', l)]
    has_numbered = len(numbered) >= 2
    # Detect prefix identifiers before names (e.g., Mr., Mrs., Dr., Sen., Rep., Pres., Prof., Hon., Sir, Lord, Lady, Capt., Lt., Gen.)
    prefix_pat = re.compile(r'\b(Mr\.|Mrs\.|Ms\.|Dr\.|Sen\.|Rep\.|Pres\.|Prof\.|Hon\.|Sir|Lord|Lady|Capt\.|Lt\.|Gen\.|Col\.|Maj\.|Rev\.)\s+[A-Z][a-zA-Z]+', text)
    prefix_hits = prefix_pat.findall(text)
    followed = (not has_table) and has_numbered and (len(prefix_hits) == 0)
    reasons = []
    if has_table: reasons.append('table detected')
    if not has_numbered: reasons.append('no numbered list')
    if prefix_hits: reasons.append(f'prefix identifiers found: {prefix_hits[:3]}')
    reason = '; '.join(reasons) if reasons else 'numbered list with no table and no prefix identifiers'
    return {'observed_followed': bool(followed), 'confidence':'medium','reason':reason,'evidence_refs':[]}
