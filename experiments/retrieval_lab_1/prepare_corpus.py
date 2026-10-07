import json, hashlib, time, sqlite3, collections, platform, sys
from pathlib import Path
ROOT=Path(r'C:\Users\王景初\Desktop\MathTutor')
LAB=ROOT/'experiments/retrieval_lab_1'; LAB.mkdir(parents=True,exist_ok=True)
if (LAB/'protected-before.json').exists():raise RuntimeError('Initial snapshot exists; refusing overwrite')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
protected={}
for folder in ['app','tests','books','data']:
 for p in (ROOT/folder).rglob('*'):
  if p.is_file() and not any(x in p.parts for x in ['__pycache__','pytest-temp']):protected[str(p.relative_to(ROOT))]={'sha256':sha(p),'bytes':p.stat().st_size}
snap={'created_at':time.time(),'protected':protected,'python':sys.version,'platform':platform.platform()}
(LAB/'protected-before.json').write_text(json.dumps(snap,ensure_ascii=False,indent=2),encoding='utf8')
pointer=json.loads((ROOT/'data/index/v12/active.json').read_text(encoding='utf8'))
gen=ROOT/'data/index/v12/generations'/pointer['generation']
data=json.loads((gen/'knowledge.json').read_text(encoding='utf8')); records=data['records']
sys.path.insert(0,str(ROOT));from app.rag.v12 import semantic_text
texts=[semantic_text(r) for r in records]
corpus={'records':records,'passages':texts,'source_generation':pointer['generation'],'v12_manifest':json.loads((gen/'manifest.json').read_text(encoding='utf8')),'passage_policy':'unchanged v12.semantic_text; same 3800 records for all models'}
(LAB/'corpus.json').write_text(json.dumps(corpus,ensure_ascii=False),encoding='utf8')
for name,source in [('development_a.json','retrieval_benchmark.json'),('development_b.json','retrieval_holdout_v121.json')]:
 d=json.loads((ROOT/'tests'/source).read_text(encoding='utf8'));d['split']='development';d['source_file_sha256']=sha(ROOT/'tests'/source);(LAB/name).write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf8')
used={(t['book'],t['pdf_page']) for name in ['development_a.json','development_b.json'] for q in json.loads((LAB/name).read_text(encoding='utf8'))['questions'] for t in q['relevant']}
pages=collections.defaultdict(list)
for r in records:
 if (r['name'],r['page']) not in used:pages[(r['name'],r['page'])].append(r)
wanted={'高等':[115,116,150,154,169,175,184,221,225,231,243,248,266,275,314,320,332,361,366,372,405,422,464,486,495,508,548,552], '数学分析中的':[95,102,115,133,146,152,171,182,208,222,238,254,281,302,330,355,382,398,411,437,483,505,529,550,569,590], '裴礼文':[34,42,55,64,73,81,108,115,127,145,156,168]}
selected=[]
for prefix,ps in wanted.items():
 for page in ps:
  matches=[(key,rs) for key,rs in pages.items() if key[0].startswith(prefix) and key[1]==page]
  if not matches:continue
  key,rs=matches[0];selected.append({'book':key[0],'pdf_page':page,'doc':rs[0]['doc']})
  print('\nBOOK',prefix,'PDF',page)
  for r in rs:print(r.get('label'),r['text'][:1400])
(LAB/'source-selection.json').write_text(json.dumps(selected,ensure_ascii=False,indent=2),encoding='utf8')
print('protected',len(protected),'records',len(records),'selected',len(selected))
