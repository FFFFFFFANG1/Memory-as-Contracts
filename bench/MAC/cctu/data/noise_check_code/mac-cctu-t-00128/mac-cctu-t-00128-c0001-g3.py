def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return {'observed_followed': None,'confidence':'unknown','reason':'no content lines','evidence_refs':[]}
    # detect tables (markdown pipe tables)
    if any('|' in l and re.search(r'\|.*\|', l) for l in lines):
        return {'observed_followed': False,'confidence':'high','reason':'table syntax detected','evidence_refs':[]}
    if any(re.match(r'^\s*[-*+\u2022]\s+', l) for l in lines):
        bullet_lines = [l for l in lines if re.match(r'^\s*[-*+\u2022]\s+', l)]
        non_bullet = [l for l in lines if not re.match(r'^\s*[-*+\u2022]\s+', l) and not re.match(r'^\s{2,}', l)]
        # allow optional heading? Be strict: any paragraph-like non-bullet line fails
        if non_bullet:
            return {'observed_followed': False,'confidence':'high','reason':f'non-bullet line present: {non_bullet[0][:80]}','evidence_refs':[]}
        # check each bullet seems to be one fact (no obvious multi-sentence paragraphs)
        for b in bullet_lines:
            content = re.sub(r'^\s*[-*+\u2022]\s+','',b)
            # multiple sentences => possible paragraph
            sentences = re.findall(r'[.!?](?:\s|$)', content)
            if len(sentences) > 2:
                return {'observed_followed': False,'confidence':'medium','reason':'bullet appears to contain multiple facts','evidence_refs':[]}
        return {'observed_followed': True,'confidence':'high','reason':'unordered bullet list with single-fact bullets','evidence_refs':[]}
    return {'observed_followed': False,'confidence':'high','reason':'no bullet markers; appears as paragraph(s)','evidence_refs':[]}
