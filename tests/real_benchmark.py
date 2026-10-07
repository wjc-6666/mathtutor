"""Run explicitly against real indexed books, outside ordinary unit tests."""
from pathlib import Path
import json,sys,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.rag.service import documents,retrieve
cases=json.loads(Path(__file__).with_name('real_cases.json').read_text(encoding='utf8'))
books={d['title']:d for d in documents()};results=[]
for case in cases:
    doc=books.get(case['book'])
    for mode in (['semantic','hybrid'] if case['category']=='模糊语义' else ['keyword','hybrid']):
        record=dict(case,mode=mode)
        try:
            if not doc:raise ValueError('资料尚未建立索引')
            hits=retrieve(case['query'],docids=[doc['id']],k=5,mode=mode)
            pages=[s['page'] for s in hits];ranks=[i+1 for i,n in enumerate(pages) if n in case['expected_pages']]
            record.update(pages=pages,rank=min(ranks) if ranks else None,result='pass' if ranks else 'fail',sources=[{'id':s['id'],'page':s['page'],'score':s['score'],'text':s['text']} for s in hits])
            if case['category']=='模糊语义' and not all(s['semantic_available'] for s in hits):record['result']='not_verified'
            if not case['expected_pages']:record.update(result='not_verified',reason='尚未人工确认原词的真实位置')
        except ValueError as e:record.update(result='not_verified',error=str(e))
        results.append(record)
out=Path(sys.argv[1]) if len(sys.argv)>1 else Path('data/real-benchmark.json')
out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps([{k:v for k,v in r.items() if k not in ['sources','criterion']} for r in results],ensure_ascii=True,indent=2))
