"""Read-only contextual control, separate from raw-dense/fixed-pool tables."""
import sys,json,time,statistics
import numpy as np
from inference import ROOT,LAB,verify_freeze,memory,sha
from metrics import score,summarize
from run_recall import dump
sys.path.insert(0,str(ROOT));from app.rag import v12
verify_freeze();dataset=json.loads((LAB/'test_c.json').read_text(encoding='utf8'));cases=[];v12.load()
for q in dataset['questions']:
 t=time.perf_counter();r=v12.search(q['query'],q['subject'],k=50);assert r['INDEX_VERSION']==v12.INDEX_VERSION
 c={key:q[key] for key in ['id','query','category','subject','source_style']};c.update(score(r['results'],q['relevant']));c['elapsed_ms']=(time.perf_counter()-t)*1000;c['top50']=[{'id':x['id'],'book':x['name'],'pdf_page':x['page'],'label':x.get('label'),'score':x['score']} for x in r['results']];cases.append(c)
lat=[c['elapsed_ms'] for c in cases]
dump(LAB/'active_v12_context.json',{'name':'unchanged active V1.2 full hybrid, contextual comparison ONLY','pool_policy':'production lexical+dense+expansion+exact+structural fusion; subject filters; NOT same pure-dense candidate pool','test_sha256':sha(LAB/'test_c.json'),'summary':summarize(cases),'cases':cases,'performance':{'mean_ms':statistics.mean(lat),'median_ms':statistics.median(lat),'p95_ms':float(np.percentile(lat,95)),**memory()}})
print(summarize(cases)['overall'])
