import re
def evaluate(trace):
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    tool_names = [tc.get('name','') for tc in trace.get('tool_calls',[]) if tc.get('name')]
    if not tool_names:
        return {'observed_followed': None,'confidence':'unknown','reason':'no tool calls to cite','evidence_refs':[]}
    # Find parenthetical citations referencing tool names
    paren_citations = re.findall(r'\(([^()]+)\)', text)
    cited_tools = [p for p in paren_citations if any(t in p for t in tool_names)]
    if not cited_tools:
        return {'observed_followed': False,'confidence':'high','reason':'no parenthetical tool-name citations found in memo','evidence_refs':[]}
    # Heuristic: check sentences with factual content have a trailing tool citation
    sentences = re.split(r'(?<=[.!?])\s+', text)
    fact_like = [s for s in sentences if re.search(r'\d|born|located|founded|year|km|miles|population|river|named', s, re.I)]
    uncited = [s for s in fact_like if not re.search(r'\(([^()]*)\)', s) or not any(t in s for t in tool_names)]
    # Check for comparative conclusion language
    comp_patterns = [r'\btherefore\b', r'\bin conclusion\b', r'\bthus\b', r'\bhence\b', r'\bmore than\b.*\bso\b', r'\bgreater than\b', r'\blonger than\b', r'\blarger than\b', r'\bshorter than\b', r'\bthe (winner|answer|comparison shows)\b', r'\bcompared to\b.*\b(is|are) (bigger|smaller|longer|shorter|greater)\b']
    comp_hits = [p for p in comp_patterns if re.search(p, text, re.I)]
    followed = True
    reasons = []
    if len(uncited) > max(1, len(fact_like)//2):
        followed = False
        reasons.append(f'{len(uncited)} fact-like sentences lack tool citation')
    if comp_hits:
        followed = False
        reasons.append(f'comparative conclusion indicators: {comp_hits[:3]}')
    if followed:
        reasons.append(f'{len(cited_tools)} parenthetical tool citations; no comparative conclusion detected')
    return {'observed_followed': followed,'confidence':'medium','reason':'; '.join(reasons),'evidence_refs':[]}
