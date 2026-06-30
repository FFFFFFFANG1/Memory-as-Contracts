def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    # Find triple backtick blocks
    blocks = re.findall(r'```[^\n`]*\n?(.*?)```', resp, flags=re.DOTALL)
    if not blocks:
        # No code block at all; check if response contains any number
        if re.search(r'\d', resp):
            return {'observed_followed': False, 'confidence':'high','reason':'numerical content not wrapped in triple backticks','evidence_refs':[resp[:200]]}
        return {'observed_followed': None,'confidence':'low','reason':'no numeric answer present to evaluate','evidence_refs':[resp[:200]]}
    # Check that response is essentially only the code block(s) with no surrounding prose
    stripped = resp.strip()
    # Remove all triple backtick blocks and see what remains
    remainder = re.sub(r'```[^\n`]*\n?.*?```', '', stripped, flags=re.DOTALL).strip()
    if remainder:
        return {'observed_followed': False,'confidence':'high','reason':f'surrounding prose detected outside code block: {remainder[:120]!r}','evidence_refs':[remainder[:200]]}
    # Verify the block content is numerical (digits, possibly with separators/units minimal)
    content = blocks[-1].strip()
    if not re.search(r'\d', content):
        return {'observed_followed': False,'confidence':'medium','reason':'code block does not contain a numerical answer','evidence_refs':[content[:200]]}
    return {'observed_followed': True,'confidence':'high','reason':'numerical answer wrapped in triple backticks with no surrounding prose','evidence_refs':[content[:200]]}
