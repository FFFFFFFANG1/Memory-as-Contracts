def evaluate(trace):
 import re
 text=(trace.get('final_response') or '').strip()
 if not text:
  return {'observed_followed':None,'confidence':'unknown','reason':'no final response','evidence_refs':[]}
 # Check for multiple paragraphs (blank line separation)
 if re.search(r'\n\s*\n', text):
  return {'observed_followed':False,'confidence':'high','reason':'multiple paragraphs detected','evidence_refs':[]}
 # Check for bullets/lists
 for line in text.split('\n'):
  s=line.lstrip()
 if re.search(r'(^|\n)\s*([-*+\u2022]|\d+[.)])\s+', text):
  return {'observed_followed':False,'confidence':'high','reason':'bullet or list marker present','evidence_refs':[]}
 # Check for tables
 if '|' in text and re.search(r'\|.*\|', text):
  return {'observed_followed':False,'confidence':'high','reason':'table-like pipes present','evidence_refs':[]}
 # Check for section delimiters (markdown headers, hr)
 if re.search(r'(^|\n)\s*#{1,6}\s+', text):
  return {'observed_followed':False,'confidence':'high','reason':'markdown header present','evidence_refs':[]}
 if re.search(r'(^|\n)\s*(---+|\*\*\*+|===+)\s*(\n|$)', text):
  return {'observed_followed':False,'confidence':'high','reason':'section delimiter present','evidence_refs':[]}
 # Count sentences
 # Remove abbreviations roughly
 cleaned=re.sub(r'\b(?:Mr|Mrs|Ms|Dr|St|Jr|Sr|vs|etc|e\.g|i\.e|U\.S|U\.K)\.', '', text)
 sentences=[s for s in re.split(r'(?<=[.!?])\s+', cleaned.strip()) if s.strip()]
 if len(sentences)>3:
  return {'observed_followed':False,'confidence':'high','reason':f'{len(sentences)} sentences exceeds 3','evidence_refs':[]}
 return {'observed_followed':True,'confidence':'high','reason':'single paragraph, <=3 sentences, no tables/bullets/delimiters','evidence_refs':[]}
