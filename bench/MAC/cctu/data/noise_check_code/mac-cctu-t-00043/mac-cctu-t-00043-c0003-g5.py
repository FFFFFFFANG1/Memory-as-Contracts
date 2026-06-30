def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '')
    if not resp.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    head = resp.strip().splitlines()[:8]
    head_text = '\n'.join(head).lower()
    has_role = bool(re.search(r'analyst|role', head_text))
    has_figure = bool(re.search(r'political figure|figure|subject|politician', head_text))
    has_verify = bool(re.search(r'verif|tool output|status', head_text))
    ok = has_role and has_figure and has_verify
    return {'observed_followed': bool(ok), 'confidence':'medium' if ok else 'medium','reason': f'role={has_role} figure={has_figure} verify={has_verify}','evidence_refs':[{'type':'final_response_head','value':'\n'.join(head)[:300]}]}
