def evaluate(trace):
    import re
    final = (trace.get('final_response') or '').strip()
    if not final:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    tool_calls = trace.get('tool_calls') or []
    av_ids, hist_ids = [], []
    def extract_ids(obj):
        out = []
        if isinstance(obj, dict):
            for k,v in obj.items():
                if isinstance(v,(dict,list)):
                    out.extend(extract_ids(v))
                elif isinstance(v,(str,int)):
                    s = str(v)
                    if re.search(r'id|identifier|reference|ref|number|no\b', k, re.I):
                        out.append(s)
                    elif re.fullmatch(r'[A-Za-z0-9_\-]{3,}', s):
                        out.append(s)
        elif isinstance(obj, list):
            for it in obj:
                out.extend(extract_ids(it))
        return out
    for tc in tool_calls:
        name = tc.get('name','')
        res = tc.get('result')
        ids = extract_ids(res) if res is not None else []
        if name == 'aviation_event_info_retriever':
            av_ids.extend(ids)
        elif name == 'merged_historical_event_tool':
            hist_ids.extend(ids)
    if not av_ids or not hist_ids:
        return {'observed_followed': None,'confidence':'unknown','reason':'could not extract ids from tool results','evidence_refs':[]}
    lines = [l for l in final.splitlines() if l.strip()]
    if not lines:
        return {'observed_followed': False,'confidence':'medium','reason':'no closing line','evidence_refs':[]}
    closing = lines[-1]
    av_hit = next((a for a in av_ids if a and a in closing), None)
    hist_hit = next((h for h in hist_ids if h and h in closing), None)
    if not av_hit or not hist_hit:
        return {'observed_followed': False,'confidence':'medium','reason':f'closing line missing ids; av={av_hit}, hist={hist_hit}','evidence_refs':[closing]}
    i1, i2 = closing.find(av_hit), closing.find(hist_hit)
    between = closing[min(i1,i2)+len(av_hit if i1<i2 else hist_hit):max(i1,i2)]
    side_by_side = len(between.strip()) <= 20
    return {'observed_followed': bool(side_by_side),'confidence':'medium' if side_by_side else 'low','reason':f'closing line: {closing}','evidence_refs':[closing]}
