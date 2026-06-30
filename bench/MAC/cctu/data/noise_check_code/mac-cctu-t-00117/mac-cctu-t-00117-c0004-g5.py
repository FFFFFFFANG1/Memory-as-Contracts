def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    t1 = 'memory_specification_combined_tool'
    t2 = 'global_language_statistics_v2'
    has_t1 = t1 in resp
    has_t2 = t2 in resp
    # single paragraph: no blank line separating text
    paragraphs = [p for p in re.split(r'\n\s*\n', resp) if p.strip()]
    single_para = len(paragraphs) == 1
    if has_t1 and has_t2 and single_para:
        return {'observed_followed': True, 'confidence':'high','reason':'single paragraph cites both tools inline','evidence_refs':[]}
    if not (has_t1 and has_t2):
        return {'observed_followed': False, 'confidence':'high','reason':f'missing inline citation(s): t1={has_t1}, t2={has_t2}','evidence_refs':[]}
    return {'observed_followed': False, 'confidence':'medium','reason':'not a single paragraph','evidence_refs':[]}
