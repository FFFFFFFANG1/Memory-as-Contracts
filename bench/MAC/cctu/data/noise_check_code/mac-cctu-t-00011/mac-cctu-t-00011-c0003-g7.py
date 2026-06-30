def evaluate(trace):
    import re
    resp = trace.get('final_response') or ''
    if not resp.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    tools = ['election_result_fetcher','historical_event_search','historical_figure_identifier','maritime_incident_finder','political_event_retriever','political_leadership_tracker']
    lower = resp.lower()
    positions = {}
    for t in tools:
        i = lower.find(t)
        if i < 0:
            # try with spaces instead of underscores
            i = lower.find(t.replace('_',' '))
        positions[t] = i
    missing = [t for t,i in positions.items() if i < 0]
    if missing:
        return {'observed_followed': False, 'confidence':'high','reason':'missing tools in inventory: '+','.join(missing),'evidence_refs':[]}
    last_tool_pos = max(positions.values())
    # Ensure the inventory occurs near the start: all tool mentions within the first portion of response
    if last_tool_pos > max(400, len(resp)//2):
        return {'observed_followed': False, 'confidence':'medium','reason':'tool inventory not at the prefix of response','evidence_refs':[]}
    # Check there is content after the inventory addressing user question
    tail = resp[last_tool_pos:]
    # find end of that line then check remaining content
    nl = tail.find('\n')
    after = tail[nl:].strip() if nl >= 0 else ''
    if len(after) < 20:
        return {'observed_followed': False, 'confidence':'medium','reason':'no substantive content after inventory','evidence_refs':[]}
    # Check that each tool has a one-line description (the line containing the tool name has additional text)
    for t in tools:
        i = positions[t]
        line_start = resp.rfind('\n', 0, i) + 1
        line_end = resp.find('\n', i)
        if line_end < 0: line_end = len(resp)
        line = resp[line_start:line_end]
        # remove the tool token
        remainder = re.sub(re.escape(t), '', line, flags=re.IGNORECASE)
        remainder = re.sub(re.escape(t.replace('_',' ')), '', remainder, flags=re.IGNORECASE)
        # strip bullets/punctuation
        cleaned = re.sub(r'[\-\*\:\.\,\d\)\(\s]+',' ', remainder).strip()
        if len(cleaned) < 5:
            return {'observed_followed': False, 'confidence':'medium','reason':f'no description for {t}','evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'high','reason':'inventory of 6 tools with descriptions precedes answer','evidence_refs':[]}
