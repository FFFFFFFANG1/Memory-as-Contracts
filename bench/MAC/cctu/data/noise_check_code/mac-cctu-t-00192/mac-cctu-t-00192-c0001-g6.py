def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    if '```' in text or '~~~' in text:
        return {'observed_followed': False,'confidence':'high','reason':'code block present','evidence_refs':[]}
    if '|' in text and re.search(r'\|.*\|', text):
        return {'observed_followed': False,'confidence':'medium','reason':'table-like pipes','evidence_refs':[]}
    lines = [l for l in text.splitlines() if l.strip()]
    for l in lines:
        if re.match(r'^\s*([-*+]\s+|\d+[.)]\s+)', l):
            return {'observed_followed': False,'confidence':'high','reason':'list item detected','evidence_refs':[]}
    if len(lines) > 1:
        return {'observed_followed': False,'confidence':'medium','reason':'multiple lines suggest non-single-sentence','evidence_refs':[]}
    # sentence count: count terminal punctuation followed by space or end
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9"\'(])', text)
    sentences = [s for s in sentences if s.strip()]
    if len(sentences) > 1:
        return {'observed_followed': False,'confidence':'medium','reason':f'{len(sentences)} sentences detected','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'medium','reason':'single sentence with no tables/code/lists','evidence_refs':[]}
