import re
def evaluate(trace):
    final=(trace.get('final_response') or '').strip()
    calls=trace.get('tool_calls') or []
    if not final:
        return {'observed_followed':None,'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    lines=[l.rstrip() for l in final.splitlines() if l.strip()]
    # find trailing bullet block
    bullets=[]
    for l in reversed(lines):
        if re.match(r'^\s*([-*\u2022]|\d+[.)])\s+',l):
            bullets.append(l)
        else:
            break
    bullets.reverse()
    if not bullets:
        return {'observed_followed':False,'confidence':'high','reason':'no trailing bulleted list','evidence_refs':[]}
    # Need references to call index and timestamp in bullets
    joined='\n'.join(bullets)
    has_index=bool(re.search(r'(call\s*(index|#|no\.?)|index\s*[:#=]?\s*\d|#\d|\bcall\s*\d)',joined,re.I))
    has_time=bool(re.search(r'(\d{4}-\d{2}-\d{2}|\d{1,2}:\d{2}(:\d{2})?|timestamp|\bUTC\b|T\d{2}:\d{2})',joined,re.I))
    if not has_index or not has_time:
        return {'observed_followed':False,'confidence':'medium','reason':f'bullets missing index({has_index}) or timestamp({has_time})','evidence_refs':[]}
    if calls and len(bullets)<len(calls):
        return {'observed_followed':False,'confidence':'medium','reason':f'{len(bullets)} bullets < {len(calls)} tool calls','evidence_refs':[]}
    return {'observed_followed':True,'confidence':'medium','reason':'trailing bulleted citation list with index and timestamp references','evidence_refs':[]}
