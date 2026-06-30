def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    lines = text.splitlines()
    bar_chars = ['█','▇','▆','▅','▄','▃','▂','#','*','=','|','■','▮']
    bar_lines = []
    for ln in lines:
        for ch in bar_chars:
            if ch*3 in ln:
                bar_lines.append(ln)
                break
    if len(bar_lines) >= 2:
        return {'observed_followed': True,'confidence':'high','reason':f'found {len(bar_lines)} ASCII bar lines','evidence_refs':bar_lines[:5]}
    if len(bar_lines) == 1:
        return {'observed_followed': False,'confidence':'low','reason':'only one bar-like line; insufficient for chart','evidence_refs':bar_lines}
    return {'observed_followed': False,'confidence':'medium','reason':'no ASCII bar chart detected in final response','evidence_refs':[]}
