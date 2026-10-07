"""Stage 1: raw dense retrieval ONLY, all models use identical frozen passages."""
import argparse,json,time,sys,statistics
from pathlib import Path
import numpy as np
from inference import LAB,ROOT,ONNX,memory,cpu_time,verify_freeze,sha
from metrics import score,summarize
def dump(path,value):path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8');tmp.replace(path)
def run(name):
 policy=verify_freeze();corp=json.loads((LAB/'corpus.json').read_text(encoding='utf8'));records=corp['records'];texts=corp['passages'];out=LAB/'runs'/name;out.mkdir(parents=True,exist_ok=True)
 started=time.time();engine=ONNX(name);print('LOADED',name,'cold',round(engine.cold_seconds,2),memory(),flush=True)
 dump(out/'adapter.json',{'inputs':[(x.name,x.shape,x.type) for x in engine.inputs],'outputs':[(x.name,x.shape,x.type) for x in engine.outputs],'providers':engine.session.get_providers(),'pooling':'mean' if name.startswith('e5') else 'cls' if name=='bge-m3' else 'last nonpadding token','query_prefix':'query: ' if name.startswith('e5') else 'none / frozen D2 instruction','tokens':384,'baseline_original_E5CPU':name=='e5-small'})
 path=out/'vectors.npy';elapsed=0;token_total=0;trunc=0;batch_size=8 if name.startswith('e5') else 4 if name=='bge-m3' else 2
 if path.exists():vectors=np.load(path);index_meta=json.loads((out/'index.json').read_text(encoding='utf8'));assert index_meta['corpus_sha256']==sha(LAB/'corpus.json')
 else:
  arrays=[];tick=time.perf_counter();cpu=cpu_time()
  for i in range(0,len(texts),batch_size):
   batch,meta=engine.embed(texts[i:i+batch_size]);arrays.append(batch);token_total+=sum(meta['tokens']);trunc+=sum(meta['truncated'])
   if (i//batch_size)%32==0 or i+batch_size>=len(texts):
    print('INDEX',name,min(i+batch_size,len(texts)),'/',len(texts),'seconds',round(time.perf_counter()-tick,1),flush=True)
    dump(out/'progress.json',{'records':min(i+batch_size,len(texts)),'total':len(texts),'elapsed_seconds':time.perf_counter()-tick,**memory()})
   if memory()['rss_bytes']>8*1024**3:raise RuntimeError('8GB CPU RSS resource guard')
   if time.perf_counter()-tick>7200:raise RuntimeError('2 hour indexing resource guard')
  vectors=np.concatenate(arrays);elapsed=time.perf_counter()-tick;np.save(path,vectors)
  index_meta={'corpus_sha256':sha(LAB/'corpus.json'),'records':len(vectors),'dimensions':vectors.shape[1],'disk_bytes':path.stat().st_size,'index_seconds':elapsed,'index_cpu_seconds':cpu_time()-cpu,'index_process_cpu_percent':100*(cpu_time()-cpu)/elapsed,'tokens':token_total,'truncated_passages':trunc,'max_length':384,**memory()};dump(out/'index.json',index_meta)
  if name=='e5-small':
   old=np.load(ROOT/'data/index/v12/generations'/corp['source_generation']/'vectors.npy');dump(out/'baseline-space-check.json',{'same_shape':old.shape==vectors.shape,'max_abs_error':float(np.max(np.abs(old-vectors))),'min_pair_cosine':float(np.min(np.sum(old*vectors,axis=1)))})
 assert len(vectors)==len(records)
 variants=[(name,None)] if name!='qwen-embedding' else [('qwen-D1',None),('qwen-D2',policy['qwen_instruction'])]
 for variant,instruction in variants:
  for setname in ['development_a','development_b','test_c']:
   dataset=json.loads((LAB/(setname+'.json')).read_text(encoding='utf8'));cases=[];latencies=[];query_vectors=[];cpu=cpu_time();tick=time.perf_counter();repeat_stable=True
   engine.embed(['数学教材'],query=True,instruction=instruction)
   for iq,q in enumerate(dataset['questions']):
    t=time.perf_counter();v,meta=engine.embed([q['query']],query=True,instruction=instruction);scores=vectors@v[0];ids=np.argsort(-scores,kind='stable')[:50];ms=(time.perf_counter()-t)*1000;latencies.append(ms)
    query_vectors.append(v[0]);rows=[records[int(i)] for i in ids];case={k:q.get(k,'unclassified') for k in ['id','category','query','subject','source_style']};case.update(score(rows,q['relevant']));case.update({'elapsed_ms':ms,'query_tokens':meta['tokens'][0],'query_truncated':meta['truncated'][0],'top50':[{'id':records[int(i)]['id'],'book':records[int(i)]['name'],'pdf_page':records[int(i)]['page'],'label':records[int(i)].get('label'),'score':float(scores[int(i)])} for i in ids]})
    if setname=='test_c':
     t=time.perf_counter();v2,_=engine.embed([q['query']],query=True,instruction=instruction);ids2=np.argsort(-(vectors@v2[0]),kind='stable')[:50];case['repeat_elapsed_ms']=(time.perf_counter()-t)*1000;case['repeat_top50_identical']=bool(np.array_equal(ids,ids2));repeat_stable&=case['repeat_top50_identical']
    cases.append(case)
    if iq%10==0:print('QUERY',variant,setname,iq+1,'/',len(dataset['questions']),flush=True)
   duration=time.perf_counter()-tick;performance={'mean_ms':statistics.mean(latencies),'median_ms':statistics.median(latencies),'p95_ms':float(np.percentile(latencies,95)),'cold_start_seconds':engine.cold_seconds,'process_cpu_percent':100*(cpu_time()-cpu)/duration,**memory()}
   result={'retriever':variant,'model':name,'phase':'dense_only','dataset':setname,'dataset_sha256':sha(LAB/(setname+'.json')),'started_at':started,'finished_at':time.time(),'index':index_meta,'performance':performance,'repeat_top50_identical':repeat_stable,'summary':summarize(cases),'cases':cases,'instruction':instruction,'pool_policy':'all 3800 records; raw TopK no exact/lexical/metadata/rules; subject intentionally not filtered; no canonicalization'}
   (LAB/'query_vectors').mkdir(exist_ok=True);np.save(LAB/'query_vectors'/f'{variant}-{setname}.npy',np.array(query_vectors))
   dump(LAB/'results_recall'/f'{variant}-{setname}.json',result);print('DONE',variant,setname,result['summary']['overall'],flush=True)
 verify_freeze()
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('name',choices=['e5-small','e5-base','bge-m3','qwen-embedding']);args=parser.parse_args()
 try:run(args.name)
 except Exception as e:
  dump(LAB/'runs'/args.name/'error.json',{'error':str(e),'time':time.time(),**memory()});raise
