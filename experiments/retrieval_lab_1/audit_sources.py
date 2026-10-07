"""Inspect existing OCR/passage representation. Never change cache or labels."""
import json,re,collections
from inference import LAB,verify_freeze,sha
verify_freeze();corpus=json.loads((LAB/'corpus.json').read_text(encoding='utf8'));dataset=json.loads((LAB/'test_c.json').read_text(encoding='utf8'));records=corpus['records'];passages=corpus['passages']
pages=[]
for book,page in dataset['source_pages']:
 selected=[(i,r) for i,r in enumerate(records) if r['name']==book and r['page']==page]
 pages.append({'book':book,'pdf_page':page,'records':[{'id':r['id'],'label':r.get('label'),'raw_ocr':r['text'],'encoded_passage':passages[i],'original_chars':len(r['text']),'passage_chars':len(passages[i]),'removed_lines':[line for line in r['text'].splitlines() if line and line not in passages[i]][:30]} for i,r in selected]})
value={'test_sha256':sha(LAB/'test_c.json'),'policy':'read-only original PDF vs existing OCR and frozen semantic_text; removed lines may include formulas and watermarks; no automatic character-count rule labels OCR-limited','source_pages':pages,'notes':'Original PDF images viewed before authorship; 29 inspected pages, 25 used source pages. Frozen author_policy says 26 topics, a metadata counting typo retained to preserve Test C bytes. Actual page count here is 25.'}
(LAB/'source_representation_audit.json').write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')
print('source pages',len(pages),'records',sum(len(p['records']) for p in pages))
