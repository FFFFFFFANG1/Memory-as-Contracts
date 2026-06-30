def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': False, 'confidence':'high','reason':'empty final response','evidence_refs':[]}
    # paragraph check: no blank line separators
    paragraphs = [p for p in re.split(r'\n\s*\n', text) if p.strip()]
    single_para = len(paragraphs) == 1
    words = re.findall(r"\b[\w'-]+\b", text)
    wc = len(words)
    in_range = 200 <= wc <= 400
    tool_calls = trace.get('tool_calls') or []
    tool_names = []
    for tc in tool_calls:
        n = tc.get('name')
        if n and n not in tool_names:
            tool_names.append(n)
    if not tool_names:
        cites = True
        missing = []
    else:
        lower = text.lower()
        missing = [n for n in tool_names if n.lower() not in lower]
        cites = len(missing) == 0
    followed = single_para and in_range and cites
    reason = f'paragraphs={len(paragraphs)} words={wc} missing_tools={missing}'
    return {'observed_followed': bool(followed), 'confidence':'high','reason':reason,'evidence_refs':[]}
