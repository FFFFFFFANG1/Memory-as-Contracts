def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '')
    if not resp.strip():
        return {"observed_followed": None, "confidence": "unknown", "reason": "empty response", "evidence_refs": []}
    low = resp.lower()
    # comparative judgment indicators
    comp_patterns = [r'\bhigher than\b', r'\blower than\b', r'\bbetter than\b', r'\bworse than\b', r'\boutperform', r'\bunderperform', r'\branked? (?:higher|lower|above|below|first|second|third|last|top|bottom)', r'\bbest(?:-| )performing\b', r'\bworst(?:-| )performing\b', r'\btop scorer', r'\bhighest scor', r'\blowest scor', r'\bcompared to\b', r'\bin comparison\b', r'\bsurpass', r'\bexceeds?\b.*\bstudent', r'\bahead of\b', r'\bbehind\b']
    hits = []
    for pat in comp_patterns:
        m = re.search(pat, low)
        if m:
            hits.append(m.group(0))
    if hits:
        return {"observed_followed": False, "confidence": "medium", "reason": f"comparative language found: {hits[:3]}", "evidence_refs": []}
    # tabular form check: look for table markers or structured rows
    has_table = ('|' in resp and resp.count('|') >= 4) or bool(re.search(r'\n\s*[-=]{3,}', resp)) or bool(re.search(r'(?m)^\s*\S+\s*[,\t]\s*\S+', resp))
    if not has_table:
        return {"observed_followed": None, "confidence": "low", "reason": "no clear tabular structure detected", "evidence_refs": []}
    return {"observed_followed": True, "confidence": "medium", "reason": "tabular output with no comparative judgment detected", "evidence_refs": []}
