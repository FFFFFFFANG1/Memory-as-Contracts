import re
def evaluate(trace):
    final = (trace.get('final_response') or '').strip()
    tool_calls = trace.get('tool_calls') or []
    if not final and not tool_calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no evidence','evidence_refs':[]}
    if len(tool_calls) > 0:
        return {'observed_followed': False, 'confidence':'high','reason':f'{len(tool_calls)} tool invocation(s) found','evidence_refs':[{'tool_calls':len(tool_calls)}]}
    # count sentences via terminal punctuation
    parts = re.findall(r'[^.!?]+[.!?]+', final)
    if not parts:
        sentences = [final] if final else []
    else:
        sentences = [p.strip() for p in parts if p.strip()]
        tail = re.sub(r'.*[.!?]+', '', final).strip()
        if tail:
            sentences.append(tail)
    n = len(sentences)
    if n <= 2:
        return {'observed_followed': True, 'confidence':'high','reason':f'{n} sentence(s), no tool calls','evidence_refs':[{'sentence_count':n}]}
    return {'observed_followed': False, 'confidence':'high','reason':f'{n} sentences exceeds 2','evidence_refs':[{'sentence_count':n}]}
