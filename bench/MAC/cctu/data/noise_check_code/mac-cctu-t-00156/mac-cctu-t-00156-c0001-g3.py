def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    # word count
    words = re.findall(r"\S+", text)
    wc = len(words)
    # markdown indicators
    has_bullet = bool(re.search(r'(^|\n)\s*[-*+]\s+', text)) or bool(re.search(r'(^|\n)\s*\d+\.\s+', text))
    has_table = '|' in text and re.search(r'\n\s*\|', text) is not None
    has_header = bool(re.search(r'(^|\n)#{1,6}\s', text))
    has_bold = '**' in text or '__' in text
    has_code = '```' in text or bool(re.search(r'`[^`]+`', text))
    # paragraph check: no blank line separating paragraphs
    paragraphs = [p for p in re.split(r'\n\s*\n', text.strip()) if p.strip()]
    single_para = len(paragraphs) == 1
    problems = []
    if wc > 80: problems.append(f'word count {wc} > 80')
    if has_bullet: problems.append('bullet/list detected')
    if has_table: problems.append('table detected')
    if has_header: problems.append('markdown header detected')
    if has_bold: problems.append('bold markdown detected')
    if has_code: problems.append('code formatting detected')
    if not single_para: problems.append('multiple paragraphs')
    followed = len(problems) == 0
    return {'observed_followed': followed, 'confidence':'high' if followed or problems else 'medium','reason': 'ok' if followed else '; '.join(problems), 'evidence_refs':[]}
