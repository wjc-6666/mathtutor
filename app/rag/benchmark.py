"""Reproducible source-page relevance metrics with per-question audit data."""
import json,statistics,time
from pathlib import Path
from app.rag.keyword import normalize

def relevance(source,target):
    return (source.get('name')==target['book'] and source.get('page')==target['pdf_page']
            and ('label' not in target or normalize(source.get('label') or '')==normalize(target['label'])))

def metrics(sources,targets):
    ranks=[next((i+1 for i,r in enumerate(sources) if relevance(r,t)),None) for t in targets]
    first=min([r for r in ranks if r]+[100000])
    return {'Recall@5':sum(bool(r and r<=5) for r in ranks)/len(targets),'Recall@10':sum(bool(r and r<=10) for r in ranks)/len(targets),
            'MRR':1/first if first<=10 else 0,'relevant_ranks':ranks}

def run(path=None,variants=None):
    from app import config
    from app.rag.service import retrieve
    from app.rag.v12 import search
    path=Path(path or config.ROOT/'tests/retrieval_benchmark.json');dataset=json.loads(path.read_text(encoding='utf8'))
    variants=variants or ['v11','keyword','hybrid','full'];results={}
    for variant in variants:
        cases=[]
        for q in dataset['questions']:
            start=time.perf_counter()
            if variant=='v11':rows=retrieve(q['query'],q['subject'],k=10)
            else:
                response=search(q['query'],q['subject'],k=10,variant=variant)
                if response['INDEX_VERSION']=='v11':raise ValueError('Benchmark 不允许把回退结果当作 V1.2')
                if variant in {'hybrid','full'} and not response['semantic_available']:raise ValueError('真实语义未启用，不能计算语义基准')
                rows=response['results']
            cases.append(dict(id=q['id'],category=q['category'],query=q['query'],**metrics(rows,q['relevant']),elapsed_ms=round((time.perf_counter()-start)*1000,2),
                              top10=[{k:r.get(k) for k in ['id','name','page','label','score','semantic_score']} for r in rows]))
        def aggregate(items):
            return dict(n=len(items),**{key:round(statistics.mean(c[key] for c in items),6) for key in ['Recall@5','Recall@10','MRR']},
                        mean_ms=round(statistics.mean(c['elapsed_ms'] for c in items),2))
        results[variant]={'overall':aggregate(cases),'categories':{cat:aggregate([c for c in cases if c['category']==cat]) for cat in sorted({c['category'] for c in cases})},'cases':cases}
    report={'dataset':{k:v for k,v in dataset.items() if k!='questions'},'questions':len(dataset['questions']),
            'metric_policy':'Mean recall over curated relevant original-PDF pages among top-K raw chunk results; MRR truncated at 10; no post-hoc label changes; no dedup before cutoff.',
            'results':results}
    output=config.DATA/'index/v12/benchmark.json';output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    return report
