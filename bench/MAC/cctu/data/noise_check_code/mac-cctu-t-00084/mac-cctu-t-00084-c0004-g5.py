def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tools = ['asteroid_name_matcher','astronomical_discovery_finder','beach_characteristic_finder','biographical_lookup','historical_contemporary_finder','historical_location_finder','literary_author_identifier','literary_work_identifier','literary_character_finder','national_symbol_finder','nearby_business_locator','power_station_data_retriever','release_year_finder']
    pre_text_parts = []
    found_tool_call = False
    for step in traj:
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if tcs:
            if content:
                pre_text_parts.append(content)
            found_tool_call = True
            break
        if content:
            pre_text_parts.append(content)
    if not found_tool_call:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls found in trajectory','evidence_refs':[]}
    pre_text = '\n'.join(pre_text_parts)
    if not pre_text.strip():
        return {'observed_followed': False,'confidence':'high','reason':'no pre-tool-call assistant content listing sub-questions','evidence_refs':[]}
    # Detect enumerated list: lines starting with 1. 2. or 1) 2)
    lines = pre_text.splitlines()
    enum_lines = [l for l in lines if re.match(r'^\s*(\d+)[\.\)]\s+', l)]
    if len(enum_lines) < 2:
        # try inline numbered
        nums = re.findall(r'(?:^|\n)\s*\d+[\.\)]\s+', pre_text)
        if len(nums) < 2:
            return {'observed_followed': False,'confidence':'high','reason':'no flat enumerated list detected before first tool call','evidence_refs':[pre_text[:200]]}
    # Check each enumerated item references a tool name
    items = enum_lines if len(enum_lines) >= 2 else re.split(r'(?:^|\n)\s*\d+[\.\)]\s+', pre_text)
    items = [i for i in items if i.strip()]
    tool_mentions = 0
    for it in items:
        if any(t in it for t in tools):
            tool_mentions += 1
    if tool_mentions >= max(2, len(items)-0) or (len(items)>0 and tool_mentions/len(items) >= 0.8):
        return {'observed_followed': True,'confidence':'medium','reason':f'enumerated list with {tool_mentions}/{len(items)} items mentioning tools','evidence_refs':[pre_text[:300]]}
    return {'observed_followed': False,'confidence':'medium','reason':f'enumerated list found but only {tool_mentions}/{len(items)} items reference a specific tool','evidence_refs':[pre_text[:300]]}
