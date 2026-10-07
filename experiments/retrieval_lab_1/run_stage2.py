"""Resource-scoped reranker cross products after all Stage 1 runs."""
import json,subprocess,sys,time
from pathlib import Path
LAB=Path(__file__).resolve().parent
names=['e5-small','e5-base','bge-m3','qwen-D1','qwen-D2']
assert all((LAB/'results_recall'/f'{n}-test_c.json').exists() for n in names),'all dense-only runs must finish first'
eligible=[n for n in names if json.loads((LAB/'results_recall'/f'{n}-test_c.json').read_text(encoding='utf8'))['summary']['overall']['Recall@50']>=.6]
# Run resource probes on the same generic pair, outside Test C, then execute
# the full frozen Top50 for the selected pools. No benchmark-specific tuning.
from inference import ONNX,verify_freeze
policy=verify_freeze();estimates=[]
for reranker in ['bge-reranker','qwen-reranker']:
 try:
  m=ONNX(reranker);t=time.perf_counter();s=m.rerank('What is a continuous function?', ['A continuous function maps sufficiently close inputs to close outputs.']* (4 if reranker=='bge-reranker' else 1),policy['qwen_instruction']);seconds=(time.perf_counter()-t)/len(s)
  long='A mathematical function is continuous when sufficiently close inputs produce close outputs. The theorem relates continuity, limits, sequences, and local properties. '*80
  t=time.perf_counter();long_scores=m.rerank('What is a continuous function?', [long]*(4 if reranker=='bge-reranker' else 1),policy['qwen_instruction']);long_seconds=(time.perf_counter()-t)/len(long_scores)
  estimates.append({'reranker':reranker,'short_pair_seconds':seconds,'full_budget_pair_seconds':long_seconds,'estimated_80queries_50candidates_repeated_seconds':long_seconds*8000,'smoke_scores':s,'cold_seconds':m.cold_seconds});del m
 except Exception as e:estimates.append({'reranker':reranker,'error':str(e)})
(LAB/'reranker-resource-probes.json').write_text(json.dumps(estimates,indent=2),encoding='utf8')
executed_plan=[]
for reranker in ['current','bge-reranker','qwen-reranker']:
 if any(x.get('error') for x in estimates if x['reranker']==reranker):continue
 if reranker!='current':
  cost=next(x for x in estimates if x['reranker']==reranker)['estimated_80queries_50candidates_repeated_seconds']
  if cost>5400:
   (LAB/(reranker+'-resource-stop.json')).write_text(json.dumps({'status':'stopped_before_Test_C_scoring','reason':'generic 384-token CPU probe estimates >90min per full repeated 80x50 pool experiment','estimated_seconds':cost}),encoding='utf8');continue
 selected=eligible[:]
 if reranker!='current' and cost>900:
  # If one repeated full pool costs >15min, narrow expensive cross products.
  # Always keep the baseline pool; one additional strongest-recall pool for
  # BGE permits disentangling embedding and combined-route improvement.
  other=[n for n in eligible if n!='e5-small']
  strongest=max(other,key=lambda n:json.loads((LAB/'results_recall'/f'{n}-test_c.json').read_text(encoding='utf8'))['summary']['overall']['Recall@50']) if other else None
  selected=['e5-small']+([strongest] if strongest and reranker=='bge-reranker' else [])
 executed_plan.append({'reranker':reranker,'eligible':eligible,'selected':selected,'reason':'resource reduction if generic 384-token estimated full repeated pool >15min; baseline plus at most one stronger pool; no per-query tuning' if selected!=eligible else 'all recall-qualified pools'})
 (LAB/'rerank_plan.json').write_text(json.dumps(executed_plan,indent=2),encoding='utf8')
 for variant in selected:
  print('START RERANK',variant,reranker,flush=True)
  with (LAB/f'{variant}-{reranker}.log').open('w',encoding='utf8') as log:
   try:
    r=subprocess.run([sys.executable,str(LAB/'run_rerank.py'),reranker,variant],cwd=LAB,stdout=log,stderr=subprocess.STDOUT,timeout=5400)
   except subprocess.TimeoutExpired:
    (LAB/f'{variant}-{reranker}-resource-stop.json').write_text(json.dumps({'status':'stopped_during_scoring','reason':'90 minute CPU combination budget exceeded; subprocess terminated; no complete quality result','seconds':5400}),encoding='utf8')
    print('RESOURCE STOP',variant,reranker,flush=True);continue
  print('END RERANK',variant,reranker,'exit',r.returncode,flush=True)
  if r.returncode:print((LAB/f'{variant}-{reranker}.log').read_text(encoding='utf8')[-1600:],flush=True)
for name in ['e5-small','e5-base','bge-m3','qwen-embedding']:
 print('REPLAY',name,flush=True);subprocess.run([sys.executable,str(LAB/'verify_repeat.py'),name],cwd=LAB,check=True)
