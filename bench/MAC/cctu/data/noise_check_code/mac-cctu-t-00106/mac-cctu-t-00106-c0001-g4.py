def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    tool_calls = trace.get('tool_calls',[]) or []
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'empty response', 'evidence_refs':[]}
    low = text.lower()
    has_log_header = any(k in low for k in ['verification log','verification_log','tool response log','tool log'])
    has_checksum = ('checksum' in low) or bool(re.search(r'\b(md5|sha-?1|sha-?256|crc32)\b', low))
    # Look for hex strings typical of checksums
    hex_hits = re.findall(r'\b[a-f0-9]{8,}\b', low)
    if not tool_calls:
        if has_log_header and has_checksum:
            return {'observed_followed': True,'confidence':'low','reason':'log present though no tool calls recorded','evidence_refs':[]}
        return {'observed_followed': None,'confidence':'unknown','reason':'no tool calls to verify against','evidence_refs':[]}
    # Need an entry per tool response
    tool_names = [tc.get('name','') for tc in tool_calls]
    mentioned = sum(1 for n in tool_names if n and n.lower() in low)
    enumerates_all = mentioned >= len(tool_calls)
    enough_checksums = len(hex_hits) >= len(tool_calls) or low.count('checksum') >= len(tool_calls)
    followed = has_log_header and has_checksum and enumerates_all and enough_checksums
    return {'observed_followed': bool(followed),'confidence':'medium','reason': f'log_header={has_log_header}, checksum_kw={has_checksum}, tools_mentioned={mentioned}/{len(tool_calls)}, hex_hits={len(hex_hits)}','evidence_refs':[]}
