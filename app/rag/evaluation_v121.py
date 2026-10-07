"""Held-out evaluation with immutable policies and graded source relevance."""
import json,hashlib,statistics,math,time
from pathlib import Path
from app.rag import benchmark,v12,v121

METRICS=['Hit@1','Recall@5','Recall@10','MRR@10','nDCG@10']
def metrics(rows,targets):
    positive=[t for t in targets if t.get('grade',3)>0]
    old=benchmark.metrics(rows,positive)
    hit=float(any(benchmark.relevance(r,t) for r in rows[:1] for t in positive))
    # One gain per annotated source target; multiple chunks on the same page
    # cannot earn repeated gain. Cutoffs still apply to raw ranked chunks.
    seen=set();gains=[]
    for r in rows[:10]:
        gain=0
        for i,t in enumerate(targets):
            if i not in seen and benchmark.relevance(r,t):seen.add(i);gain=max(gain,2**t.get('grade',3)-1)
        gains.append(gain)
    ideal=sorted([2**t.get('grade',3)-1 for t in targets],reverse=True)[:10]
    dcg=sum(g/math.log2(i+2) for i,g in enumerate(gains));idcg=sum(g/math.log2(i+2) for i,g in enumerate(ideal))
    return {'Hit@1':hit,'Recall@5':old['Recall@5'],'Recall@10':old['Recall@10'],'MRR@10':old['MRR'],'nDCG@10':dcg/idcg if idcg else 0,'relevant_ranks':old['relevant_ranks']}
def aggregate(cases):
    return {'n':len(cases),**{key:round(statistics.mean(c[key] for c in cases),6) for key in METRICS}}
def freeze(path):
    d=v121.load();value={'policy_hash':v121.policy_hash(),'generation':d['manifest']['generation'],'frozen_at':time.time(),'weights':v121.WEIGHTS,'holdout_seen':False}
    v121._atomic(Path(path),value);return value
def run(path,freeze_path=None):
    path=Path(path);dataset=json.loads(path.read_text(encoding='utf8'));before=v121.policy_hash()
    if dataset.get('split')=='holdout':
        frozen=json.loads(Path(freeze_path).read_text(encoding='utf8'))
        if frozen['policy_hash']!=before or dataset['frozen_policy_hash']!=before:raise ValueError('规则变动，holdout已失去独立性')
        if dataset['created_at']<=frozen['frozen_at']:raise ValueError('holdout必须在冻结后建立')
    results={}
    for version in ['v12','v121']:
        cases=[]
        for q in dataset['questions']:
            response=v12.search(q['query'],q['subject'],k=10) if version=='v12' else v121.search(q['query'],q['subject'],k=10,strict=True)
            cases.append(dict(id=q['id'],category=q['category'],query=q['query'],**metrics(response['results'],q['relevant']),top10=[{k:r.get(k) for k in ['id','name','page','label','score']} for r in response['results']],elapsed_ms=response['elapsed_ms']))
        results[version]={'overall':aggregate(cases),'categories':{cat:aggregate([c for c in cases if c['category']==cat]) for cat in sorted({c['category'] for c in cases})},'cases':cases}
    if v121.policy_hash()!=before:raise ValueError('评估中途策略改变')
    return {'split':dataset.get('split','development'),'policy_hash':before,'dataset_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'questions':len(dataset['questions']),'metric_policy':'raw records cutoff; positives grade>0; unique annotated-page gains for nDCG; MRR@10; partial curated relevance','results':results}
