import json,uuid,os
from pathlib import Path
from app.config import ROOT,DATA,BOOKS
from app.pdf.extract import pages
from app.pdf.pipeline import file_hash,cache_dir,load,book_title
from app.rag.chunk import chunks
from app.rag.keyword import scores
from app.llm.providers import embedder
from app.database.store import connect
INDEX_REVISION='ocr-structure-hybrid-v6'
def index_file(path,subject):
    if subject not in {'analysis','algebra'}:raise ValueError('学科错误')
    path=Path(path).resolve()
    if not path.is_relative_to((BOOKS/subject).resolve()):raise ValueError('资料必须位于所选学科目录')
    digest=file_hash(path);emb=embedder()
    with connect() as c:old=c.execute('SELECT * FROM documents WHERE path=?',(str(path),)).fetchone()
    cache=cache_dir(path,DATA/'ocr',digest) if path.suffix.lower()=='.pdf' else None
    manifest=load(cache/'manifest.json') if cache else None
    if old and old['digest']==digest and old['embedding']==emb.identity and old['index_revision']==INDEX_REVISION and (cache is None or (manifest and manifest['status']=='completed')):return dict(old)
    parts=[];empty=0;total=0;chapter=None;section=None
    for page in pages(path):
        total+=1;page=dict(page,chapter=chapter,section=section);extracted=chunks(page)
        if not extracted:empty+=1
        if extracted:chapter=extracted[-1]['chapter'];section=extracted[-1]['section']
        parts.extend(extracted)
    vectors=emb.embed([p['text'] for p in parts]) if parts else []
    if len(vectors)!=len(parts):raise ValueError('向量数量错误')
    manifest=load(cache/'manifest.json') if cache else None
    diagnostics=dict(manifest or {},chunk_count=len(parts),index_state='partial' if manifest and manifest['failed_pages'] else 'ready' if parts else 'empty',embedding=emb.identity,semantic_available=not emb.identity.startswith('hash'))
    status=f'已索引 {len(parts)} 片段'+(f"；OCR {manifest['ocr_success']}/{len(manifest['needs_ocr_pages'])}；失败 {len(manifest['failed_pages'])}" if manifest else '')
    if not parts:status='需要 OCR 或人工检查：无可用文字'
    docid=old['id'] if old else str(uuid.uuid4());title=book_title(path)
    with connect() as c:
        if old:c.execute('DELETE FROM documents WHERE id=?',(docid,))
        c.execute('INSERT INTO documents(id,path,name,subject,digest,embedding,status,title,diagnostics,index_revision) VALUES(?,?,?,?,?,?,?,?,?,?)',(docid,str(path),path.name,subject,digest,emb.identity,status,title,json.dumps(diagnostics,ensure_ascii=False),INDEX_REVISION))
        c.executemany('INSERT INTO chunks(id,doc,title,page,section,subsection,text,vector,chapter,content_type,label,page_end,printed_page,method) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',[(str(uuid.uuid4()),docid,title,p.get('page'),p['section'],p['subsection'],p['text'],json.dumps(v),p['chapter'],p['content_type'],p['label'],p['pdf_page_end'],p.get('printed_page'),p.get('method','text')) for p,v in zip(parts,vectors)])
    return {'id':docid,'name':path.name,'title':title,'status':status,'diagnostics':diagnostics}
def scan(subject='all'):
    if subject not in {'all','analysis','algebra'}:raise ValueError('未知学科')
    result=[]
    for s in (['analysis','algebra'] if subject=='all' else [subject]):
        for path in sorted((BOOKS/s).rglob('*')):
            if path.suffix.lower() in {'.pdf','.txt','.md'}:
                try:result.append(index_file(path,s))
                except Exception as e:result.append({'name':path.name,'status':'索引失败：'+str(e)})
    return result
def documents():
    with connect() as c:rows=c.execute('SELECT id,name,subject,status,title,diagnostics FROM documents ORDER BY name').fetchall()
    result=[]
    for row in rows:
        d=dict(row);d['diagnostics']=json.loads(d['diagnostics'] or '{}');result.append(d)
    return result
def remove(docid):
    with connect() as c:c.execute('DELETE FROM documents WHERE id=?',(docid,))
def retrieve(query,subject='all',docids=None,k=6,mode='hybrid'):
    if mode not in {'hybrid','keyword','vector','semantic'}:raise ValueError('未知检索模式')
    emb=embedder()
    if mode=='semantic' and emb.identity.startswith('hash'):raise ValueError('hash 是字符基线，不是语义模型。请配置 local provider；无需付费 API')
    with connect() as c:
        sql='SELECT chunks.*,documents.name,documents.subject,documents.embedding FROM chunks JOIN documents ON doc=documents.id'
        rows=[dict(r) for r in c.execute(sql) if (subject=='all' or r['subject']==subject) and (not docids or r['doc'] in docids)]
    if not rows:return []
    keyword=scores(query,rows) if mode in {'hybrid','keyword'} else [0]*len(rows);vector=[0.]*len(rows)
    if mode!='keyword':
        q=emb.embed_query(query) if hasattr(emb,'embed_query') else emb.embed([query])[0]
        for i,row in enumerate(rows):
            if row['embedding']!=emb.identity:raise ValueError('Embedding 配置已改变，请重新建立索引')
            v=json.loads(row['vector'])
            if len(v)!=len(q):raise ValueError('向量维度不一致，请重建索引')
            vector[i]=sum(a*b for a,b in zip(q,v))
    threshold=float(os.getenv('RETRIEVAL_MIN_SCORE','.2'))
    vranked=sorted((i for i,s in enumerate(vector) if s>=threshold),key=lambda i:vector[i],reverse=True)
    kranked=sorted((i for i,s in enumerate(keyword) if s>0),key=lambda i:keyword[i],reverse=True);ranks={}
    for group,weight in [(vranked,.25 if emb.identity.startswith('hash') else 1),(kranked,1)]:
        for rank,i in enumerate(group[:100],1):ranks[i]=ranks.get(i,0)+weight/(60+rank)
    candidates=kranked if mode=='keyword' else vranked if mode in {'vector','semantic'} else sorted(ranks,key=lambda i:ranks[i],reverse=True)
    if mode=='hybrid':
        # Hash collisions must not displace useful BM25 hits. True hybrid fusion
        # is enabled only with a real semantic provider.
        candidates=kranked if emb.identity.startswith('hash') else sorted(candidates,key=lambda i:(keyword[i]>=140,keyword[i]>=40,ranks[i],keyword[i]),reverse=True)
    result=[]
    for i in candidates[:k]:
        d=dict(rows[i]);d.pop('vector');d.pop('embedding')
        d.update(source_file=d['name'],book_name=d['title'],pdf_page_start=d['page'],pdf_page_end=d['page_end'] or d['page'],score=round(keyword[i] if mode=='keyword' or (mode=='hybrid' and emb.identity.startswith('hash')) else vector[i] if mode in {'vector','semantic'} else ranks[i]*30,4),keyword_score=round(keyword[i],4),vector_score=round(vector[i],4),semantic_available=not emb.identity.startswith('hash'),retrieval_mode=mode,retrieval_backend='keyword-fallback' if mode=='hybrid' and emb.identity.startswith('hash') else mode)
        result.append(d)
    return result
