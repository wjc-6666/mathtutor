"""Stage 2 only: fixed persisted Top50; neural scoring cannot add candidates."""
import json,sys,time,inspect,argparse,statistics,hashlib
import numpy as np
from inference import LAB,ROOT,ONNX,memory,cpu_time,verify_freeze,sha
from metrics import score,summarize
from run_recall import dump
sys.path.insert(0,str(ROOT))
from app.rag import v12
class CachedQuery:
 def __init__(self,vector):self.vector=vector
 def embed(self,texts,query=False):return self.vector.reshape(1,-1)
def rules_adapter(corpus):
 source=inspect.getsource(v12.search)
 # Keep ALL original scoring weights/profile/expansion. Replace only
 # candidate selection and use the already frozen raw semantic query.
 source=source.replace("semantic_query=semantic_text(exact_records[0]) if variant=='full' and exact_records else query","semantic_query=query")
 original="recalled=sorted([x for x in candidates if x[0] in pools],key=lambda x:(x[1]['exact_score']==1,fusion[x[0]]),reverse=True)[:50]"
 assert original in source
 source=source.replace(original,"recalled=[x for x in candidates if x[0] in fixed_pool]")
 ns=dict(v12.__dict__);ns['fixed_pool']=set();ns['load']=lambda:ns['lab_data'];exec(source,ns)
 (LAB/'frozen_current_rerank.py.txt').write_text(source,encoding='utf8')
 base={'records':corpus['records'],'parents':{},'edges':json.loads((ROOT/'data/index/v12/generations'/corpus['source_generation']/'knowledge.json').read_text(encoding='utf8'))['edges'],'bm25':v12.BM25(corpus['records'])}
 return ns,base
def run(reranker,variants):
 policy=verify_freeze();corpus=json.loads((LAB/'corpus.json').read_text(encoding='utf8'));records=corpus['records'];byid={r['id']:i for i,r in enumerate(records)};model=ONNX(reranker) if reranker!='current' else None
 if model:dump(LAB/'runs'/reranker/'adapter.json',{'inputs':[(x.name,x.shape,x.type) for x in model.inputs],'outputs':[(x.name,x.shape,x.type) for x in model.outputs],'cold_seconds':model.cold_seconds,'score':'raw classifier logit' if reranker=='bge-reranker' else 'yes logit minus no logit, ranking-equivalent to binary softmax','max_tokens':384,'instruction':policy['qwen_instruction']})
 ns,base=rules_adapter(corpus) if not model else (None,None)
 run_start=time.time()
 for variant in variants:
  recalled=json.loads((LAB/'results_recall'/f'{variant}-test_c.json').read_text(encoding='utf8'))
  if recalled['summary']['overall']['Recall@50']<.6:
   dump(LAB/'results_rerank'/f'{variant}-{reranker}-skipped.json',{'retriever':variant,'reranker':reranker,'status':'skipped','reason':'frozen recall gate <60%'});continue
  qs=json.loads((LAB/'test_c.json').read_text(encoding='utf8'))['questions'];cached={x['id']:x for x in recalled['cases']};cases=[];lat=[];repeat=True;cpu=cpu_time();tick=time.perf_counter()
  if not model:
   cache_path=LAB/'query_vectors'/f'{variant}-test_c.npy'
   if not cache_path.exists():
    dense=ONNX(recalled['model']);instruction=policy['qwen_instruction'] if variant=='qwen-D2' else None
    query_vectors=np.concatenate([dense.embed([q['query']],query=True,instruction=instruction)[0] for q in qs]);cache_path.parent.mkdir(exist_ok=True);np.save(cache_path,query_vectors)
    del dense
   query_vectors=np.load(cache_path);vectors=np.load(LAB/'runs'/recalled['model']/'vectors.npy',mmap_mode='r')
   tick=time.perf_counter();cpu=cpu_time()
  # Preserve partial progress and estimate full CPU cost before committing to
  # optional cross products. Threshold was fixed as experience budget, not a
  # relevance-dependent stop condition.
  output=LAB/'results_rerank'/f'{variant}-{reranker}.json'
  if output.exists():print('EXISTS',output.name,flush=True);continue
  for iq,q in enumerate(qs):
   pool=cached[q['id']]['top50'];indices=[byid[x['id']] for x in pool];rows=[records[i] for i in indices];start=time.perf_counter()
   if model:
    batchsize=4 if reranker=='bge-reranker' else 1;scores=[]
    for offset in range(0,len(indices),batchsize):scores.extend(model.rerank(q['query'],[corpus['passages'][i] for i in indices[offset:offset+batchsize]],policy['qwen_instruction']))
    order=np.argsort(-np.array(scores),kind='stable');ranked=[rows[int(i)] for i in order];rank_scores=[float(scores[int(i)]) for i in order]
   else:
    # Recover the cosine scores for ALL records from the persisted query
    # embedding cache generated afresh from the same frozen raw query.
    vector=query_vectors[iq];ns['lab_data']=dict(base,engine=CachedQuery(vector),vectors=vectors);ns['fixed_pool']=set(indices)
    response=ns['search'](q['query'],'all',k=50);ranked=response['results'];rank_scores=[r['score'] for r in ranked]
   ms=(time.perf_counter()-start)*1000;lat.append(ms);assert {r['id'] for r in ranked}=={r['id'] for r in rows}
   c={k:q[k] for k in ['id','category','query','subject','source_style']};c.update(score(ranked,q['relevant']));c.update({'elapsed_ms':ms,'total_search_ms':ms+cached[q['id']]['elapsed_ms'],'candidate_first_rank':cached[q['id']]['first_relevant_rank'],'candidate_ids':[r['id'] for r in rows],'top50':[{'id':r['id'],'book':r['name'],'pdf_page':r['page'],'label':r.get('label'),'score':s} for r,s in zip(ranked,rank_scores)]})
   # Repetition on all Test C cases. For the rule adapter deterministic sort is
   # replayed directly; the neural weights perform a second inference.
   if model:
    second=[]
    for offset in range(0,len(indices),batchsize):second.extend(model.rerank(q['query'],[corpus['passages'][i] for i in indices[offset:offset+batchsize]],policy['qwen_instruction']))
    c['repeat_top50_identical']=bool(np.array_equal(order,np.argsort(-np.array(second),kind='stable')));repeat&=c['repeat_top50_identical']
   else:
    second=ns['search'](q['query'],'all',k=50)['results']
    c['repeat_top50_identical']=[r['id'] for r in ranked]==[r['id'] for r in second];repeat&=c['repeat_top50_identical']
   cases.append(c)
   dump(LAB/'runs'/reranker/'progress.json',{'variant':variant,'completed':len(cases),'total':len(qs),'elapsed_seconds':time.perf_counter()-tick,**memory()})
   if iq%5==0:print('RERANK',variant,reranker,iq+1,'/',len(qs),'query_ms',round(ms),flush=True)
   if memory()['rss_bytes']>8*1024**3:raise RuntimeError('8GB RSS guard')
  elapsed=time.perf_counter()-tick
  result={'retriever':variant,'reranker':reranker,'phase':'fixed_top50_rerank','test_sha256':sha(LAB/'test_c.json'),'pool_source_sha256':sha(LAB/'results_recall'/f'{variant}-test_c.json'),'summary':summarize(cases),'cases':cases,'repeat_top50_identical':repeat,'performance':{'mean_rerank_ms':statistics.mean(lat),'median_rerank_ms':statistics.median(lat),'p95_rerank_ms':float(np.percentile(lat,95)),'mean_total_ms':statistics.mean(c['total_search_ms'] for c in cases),'p95_total_ms':float(np.percentile([c['total_search_ms'] for c in cases],95)),'cold_seconds':model.cold_seconds if model else None,'process_cpu_percent':100*(cpu_time()-cpu)/elapsed,**memory()},'started_at':run_start,'finished_at':time.time()};dump(output,result);print('DONE',variant,reranker,result['summary']['overall'],flush=True)
 verify_freeze()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('reranker',choices=['current','bge-reranker','qwen-reranker']);p.add_argument('variants',nargs='+');args=p.parse_args();run(args.reranker,args.variants)
