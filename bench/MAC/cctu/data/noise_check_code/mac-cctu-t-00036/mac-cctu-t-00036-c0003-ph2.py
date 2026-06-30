def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    low = text.lower()
    # Detect a table: markdown pipe table or HTML table
    has_pipe_table = bool(re.search(r'\|.*\|', text)) and text.count('|') >= 4 and bool(re.search(r'\|\s*-{2,}', text))
    has_html_table = '<table' in low
    has_table = has_pipe_table or has_html_table
    mentions_height = 'height' in low
    mentions_weight = 'weight' in low
    classification_terms = ['underweight','overweight','obese','obesity','normal weight','healthy weight','healthy range','normal range','classification','category','categori','bmi category','interpret']
    found_class = [t for t in classification_terms if t in low]
    if not has_table:
        return {'observed_followed': False, 'confidence':'high','reason':'no structured table found','evidence_refs':[]}
    if not (mentions_height and mentions_weight):
        return {'observed_followed': False, 'confidence':'medium','reason':'table missing height/weight labels','evidence_refs':[]}
    if found_class:
        return {'observed_followed': False, 'confidence':'high','reason':f'interpretive classification present: {found_class}','evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'high','reason':'structured table with raw height/weight and no classification','evidence_refs':[]}
