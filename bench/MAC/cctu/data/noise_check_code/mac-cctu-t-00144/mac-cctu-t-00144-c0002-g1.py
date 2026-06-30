import re
def evaluate(trace):
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    tool_names = {tc.get('name') for tc in (trace.get('tool_calls') or []) if tc.get('name')}
    if not tool_names:
        tool_names = {'animal_info_tool','aviation_incident_info_retriever','earthquake_data_retriever','historical_event_data_retriever','merged_event_data_retriever','ocean_depth_info'}
    # Find numeric figures (ignore numbers inside parentheses themselves)
    # Mask parenthetical content to avoid catching numbers used as citations
    masked = re.sub(r'\([^()]*\)', lambda m: ' '*len(m.group(0)), text)
    num_pattern = re.compile(r'(?<![A-Za-z_])-?\d[\d,]*(?:\.\d+)?')
    issues = []
    checked = 0
    for m in num_pattern.finditer(masked):
        checked += 1
        end = m.end()
        tail = text[end:end+200]
        # Allow optional unit/word then a parenthetical containing a tool name
        mp = re.match(r'[^()\n]{0,60}?\(([^()]*)\)', tail)
        ok = False
        if mp:
            inside = mp.group(1)
            if any(tn in inside for tn in tool_names):
                ok = True
        if not ok:
            issues.append(m.group(0))
    if checked == 0:
        return {'observed_followed': None,'confidence':'unknown','reason':'no numeric figures found in response','evidence_refs':[]}
    if not issues:
        return {'observed_followed': True,'confidence':'high','reason':f'all {checked} numeric figures annotated with tool name','evidence_refs':[]}
    return {'observed_followed': False,'confidence':'high','reason':f'{len(issues)}/{checked} numeric figures lack tool annotation: '+', '.join(issues[:5]),'evidence_refs':[]}
