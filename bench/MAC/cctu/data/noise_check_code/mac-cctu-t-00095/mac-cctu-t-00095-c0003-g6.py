def evaluate(trace):
    import re
    final = (trace.get('final_response') or '')
    if not final.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    low = final.lower()
    # Detect markdown table: at least one row with | and a separator line
    lines = final.splitlines()
    has_sep = any(re.match(r'^\s*\|?\s*:?-{2,}', l) and '|' in l for l in lines)
    pipe_rows = sum(1 for l in lines if l.count('|') >= 2)
    has_table = has_sep and pipe_rows >= 2
    mentions_lineage = any(k in low for k in ['ownership','parent company','lineage','parent'])
    if has_table and mentions_lineage:
        return {'observed_followed': True,'confidence':'high','reason':'ownership lineage table present','evidence_refs':[]}
    if not has_table and not mentions_lineage:
        return {'observed_followed': False,'confidence':'high','reason':'no table and no ownership lineage references','evidence_refs':[]}
    if not has_table:
        return {'observed_followed': False,'confidence':'medium','reason':'ownership mentioned but no markdown table','evidence_refs':[]}
    return {'observed_followed': False,'confidence':'low','reason':'table present but no ownership/parent lineage terms','evidence_refs':[]}
