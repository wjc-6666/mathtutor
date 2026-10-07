import json,uuid,os,io
from pathlib import Path
from fastapi import FastAPI,UploadFile,File,Form,HTTPException
from fastapi.responses import FileResponse,Response
from pydantic import BaseModel,Field
from app.config import ROOT,DATA,BOOKS
from app.database.store import connect
from app.rag.service import scan,index_file,retrieve,documents,remove
from app.prompts.tutor import messages
from app.llm.providers import chat_model
from app.vision.service import recognize
import threading,time

index_jobs={'state':'idle'}
job_lock=threading.Lock()

app=FastAPI(title='MathTutor V1.2')
@app.post('/api/index-job')
def start_index_job():
    with job_lock:
        if index_jobs['state']=='running':return index_jobs
        index_jobs.update(state='running',started_at=time.time(),results=[])
    def run():
        try:index_jobs.update(results=scan(),state='completed',updated_at=time.time())
        except Exception as e:index_jobs.update(state='failed',error=str(e),updated_at=time.time())
    threading.Thread(target=run,daemon=True).start()
    return index_jobs

@app.get('/api/diagnostics')
def diagnostics():
    from app.pdf.pipeline import load
    caches=[load(p) for p in (DATA/'ocr').glob('*/*/manifest.json')]
    return {'job':dict(index_jobs),'books':[r for r in caches if r],'documents':documents()}

class DebugQuery(BaseModel):
    question:str=Field(min_length=1,max_length=2000)
    subject:str='all'
    documents:list[str]=Field(default_factory=list)
    mode:str='hybrid'
    k:int=Field(default=6,ge=1,le=30)
@app.post('/api/retrieval-debug')
def debug(q:DebugQuery):return retrieve(q.question,q.subject,q.documents,q.k,q.mode)

@app.post('/api/retrieval-debug-v2')
def debug_v2(q:DebugQuery):
    from app.rag.v12 import search
    from app.rag.v121 import status,search as candidate_search
    if status()['active_version']=='v121':return candidate_search(q.question,q.subject,q.documents,q.k,pointer='active')
    return search(q.question,q.subject,q.documents,q.k)

class SemanticDebugQuery(DebugQuery):
    experiment:str=Field(default='E',pattern='^[A-E]$')
    disabled_rules:list[str]=Field(default_factory=list)

@app.post('/api/retrieval-debug-v21')
def debug_v21(q:SemanticDebugQuery):
    from app.rag.v121 import search
    return search(q.question,q.subject,q.documents,q.k,experiment=q.experiment,disabled_rules=q.disabled_rules)

@app.post('/api/similar-problems-v21')
def similar_v21(q:DebugQuery):
    from app.rag.v121 import similar
    return similar(q.question,q.subject,q.documents,min(q.k,5))

@app.post('/api/similar-problems')
def similar_problems(q:DebugQuery):
    from app.rag.v12 import similar
    from app.rag.v121 import status,similar as candidate_similar
    if status()['active_version']=='v121':return candidate_similar(q.question,q.subject,q.documents,min(q.k,5),pointer='active')
    return similar(q.question,q.subject,q.documents,min(q.k,5))

@app.get('/api/knowledge-map')
def knowledge_map():
    from app.rag.v12 import map_summary
    return map_summary()

@app.get('/api/topics/{name}')
def topic_view(name:str,subject:str='all'):
    from app.rag.v12 import topic
    return topic(name,subject)

@app.get('/api/retrieval-status')
def retrieval_status():
    from app.rag.v121 import status
    return status()

@app.get('/api/chunks/{chunkid}')
def get_chunk(chunkid:str):
    with connect() as c:
        row=c.execute('SELECT chunks.id,doc,chunks.title,page,page_end,chapter,section,text,content_type,label,method,documents.name,documents.subject FROM chunks JOIN documents ON doc=documents.id WHERE chunks.id=?',(chunkid,)).fetchone()
    if not row:
        from app.rag.v12 import load
        try:record=load()['byid'].get(chunkid)
        except Exception:record=None
        if not record:raise HTTPException(404,'Chunk 不存在或已删除')
        return record
    return dict(row)

def managed_pdf(docid:str):
    # The client supplies an ID only. Resolve the stored path and reject symlink
    # or traversal escapes from the managed books directory.
    with connect() as c:row=c.execute('SELECT path FROM documents WHERE id=?',(docid,)).fetchone()
    if not row:raise HTTPException(404,'资料不存在')
    try:
        stored=Path(row['path']);path=(stored if stored.is_absolute() else ROOT/stored).resolve()
    except (TypeError,ValueError,OSError):raise HTTPException(404,'资料路径无效') from None
    if not path.is_relative_to(BOOKS.resolve()):raise HTTPException(404,'资料不在受管教材目录')
    if path.suffix.lower()!='.pdf':raise HTTPException(400,'该资料不是 PDF')
    if not path.is_file():raise HTTPException(404,'原始 PDF 文件不存在')
    return path

@app.get('/api/documents/{docid}/pdf')
def original_pdf(docid:str):
    path=managed_pdf(docid)
    return FileResponse(path,media_type='application/pdf',filename=path.name,content_disposition_type='inline')

@app.get('/api/documents/{docid}/page/{page}')
def page_image(docid:str,page:int):
    """page=1 is the first original PDF page. Render only the requested page."""
    if page<1:raise HTTPException(404,'PDF 页码必须从 1 开始')
    path=managed_pdf(docid)
    import pypdfium2
    try:
        with pypdfium2.PdfDocument(str(path)) as pdf:
            if page>len(pdf):raise HTTPException(404,'页码超出 PDF 总页数')
            original=pdf[page-1]
            try:
                # Independent of OCR settings; cap the raster to 4096 pixels.
                scale=min(2.5,4096/max(original.get_size()))
                bitmap=original.render(scale=scale)
                try:
                    image=bitmap.to_pil()
                    try:
                        output=io.BytesIO();image.save(output,format='PNG');raw=output.getvalue()
                    finally:image.close()
                finally:bitmap.close()
            finally:original.close()
    except pypdfium2.PdfiumError:raise HTTPException(500,'原始 PDF 无法读取或渲染') from None
    # No OCR, PDF rewriting, preview cache, or other persistent data writes.
    return Response(raw,media_type='image/png',headers={'Cache-Control':'no-cache'})
@app.exception_handler(ValueError)
async def invalid(request,exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=400,content={'detail':str(exc)})

@app.get('/')
def home(): return FileResponse(Path(__file__).parent/'ui/index.html')
@app.get('/api/status')
def status(): return {'llm':os.getenv('LLM_PROVIDER','offline'),'embedding':os.getenv('EMBEDDING_PROVIDER','hash')}
@app.get('/api/documents')
def docs(): return documents()
@app.post('/api/index')
def rebuild(): return scan()
@app.delete('/api/documents/{docid}')
def delete(docid:str): remove(docid); return {'ok':True}
@app.get('/api/documents/{docid}/file')
def view(docid:str):
    with connect() as c: row=c.execute('SELECT * FROM documents WHERE id=?',(docid,)).fetchone()
    if not row: raise HTTPException(404,'资料不存在')
    path=Path(row['path']).resolve()
    if not path.is_relative_to(BOOKS.resolve()) or not path.is_file(): raise HTTPException(404,'资料不存在')
    return FileResponse(path,filename=path.name)

@app.post('/api/upload')
def upload(file:UploadFile=File(...),subject:str=Form(...)):
    if subject not in {'analysis','algebra'}: raise ValueError('请选择数学分析或高等代数')
    name=Path((file.filename or '').replace('\\','/')).name
    if Path(name).suffix.lower() not in {'.pdf','.txt','.md'}: raise ValueError('仅支持 PDF/TXT/MD')
    folder=BOOKS/subject;folder.mkdir(parents=True,exist_ok=True)
    path=folder/name
    if path.exists(): raise ValueError('同名文件已存在，请重命名后上传')
    size=0; created=False
    try:
        with path.open('xb') as out:
            created=True
            while block:=file.file.read(1024*1024):
                size+=len(block)
                if size>200*1024*1024: raise ValueError('文件超过 200 MB')
                out.write(block)
    except Exception:
        if created and path.exists(): path.unlink()
        raise
    try: return index_file(path,subject)
    except Exception as e: raise ValueError('文件已保存，但索引失败，可修复配置后重建：'+str(e)) from None

@app.post('/api/vision')
def vision(file:UploadFile=File(...)):
    raw=file.file.read(10*1024*1024+1)
    if len(raw)>10*1024*1024: raise ValueError('图片超过 10 MB')
    mime='image/png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg' if raw.startswith(b'\xff\xd8\xff') else None
    if not mime: raise ValueError('仅支持 PNG/JPEG 图片')
    return recognize(raw,mime)

@app.get('/api/chats')
def chats():
    with connect() as c: return [dict(r) for r in c.execute('SELECT * FROM chats ORDER BY rowid DESC')]
@app.get('/api/chats/{chatid}')
def history(chatid:str):
    with connect() as c: rows=c.execute('SELECT * FROM messages WHERE chat=? ORDER BY id',(chatid,)).fetchall()
    return [dict(r,sources=json.loads(r['sources'])) for r in rows]

class Question(BaseModel):
    question:str=Field(min_length=1,max_length=20000)
    subject:str='all'
    mode:str='detail'
    chatid:str|None=None
    documents:list[str]=Field(default_factory=list)
    retrieval_version:str='auto'

@app.post('/api/chat')
def ask(q:Question):
    if q.subject not in {'all','analysis','algebra'}: raise ValueError('未知学科')
    cid=q.chatid or str(uuid.uuid4())
    with connect() as c:
        existing=c.execute('SELECT id FROM chats WHERE id=?',(cid,)).fetchone()
        if q.chatid and not existing: raise ValueError('对话不存在')
        past=[dict(role=r['role'],content=r['content']) for r in c.execute('SELECT role,content FROM messages WHERE chat=? ORDER BY id',(cid,))]
    # 多轮提示时仍检索原题；选多本资料时每本独立检索，防止单本占满。
    query='\n'.join([r['content'] for r in past if r['role']=='user'][-2:]+[q.question])
    if q.retrieval_version not in {'auto','v11'}:raise ValueError('未知检索版本')
    from app.rag.v12 import search
    from app.rag.v121 import status,search as candidate_search
    evidence=None;retrieval_info=status()
    if retrieval_info['active_version']=='v121':
        def search(query,subject='all',docids=None,k=10):return candidate_search(query,subject,docids,k,pointer='active')
    if q.retrieval_version!='v11' and retrieval_info['active_version'] in {'v12','v121'}:
        responses=[search(query,q.subject,[did],k=4) for did in q.documents[:6]] if q.documents else [search(query,q.subject,k=10)]
        sources=[s for r in responses for s in r['results']]
        evidence={key:[x for r in responses for x in r['evidence_bundle'][key]] for key in responses[0]['evidence_bundle']}
        for key in ['core_theory','similar_problems','method_related']:
            for source in evidence[key]:
                if not any(x['id']==source['id'] for x in sources):sources.append(source)
        retrieval_info={key:responses[0][key] for key in ['INDEX_VERSION','semantic_available','fallback_reason','query_profile']}
    else:
        sources=[]
        if q.documents:
            for did in q.documents[:6]: sources.extend(retrieve(query,q.subject,[did],k=2))
        else: sources=retrieve(query,q.subject)
    answer=chat_model().answer(messages(q.question,q.mode,sources,past,evidence))
    if evidence and os.getenv('LLM_PROVIDER','offline')=='offline':
        from app.rag.v12 import offline_navigation
        answer=offline_navigation(q.question,q.mode,retrieval_info['query_profile'],evidence,sources)
    with connect() as c:
        c.execute('INSERT OR IGNORE INTO chats VALUES(?,?)',(cid,q.question[:40]))
        c.execute('INSERT INTO messages(chat,role,content,sources) VALUES(?,?,?,?)',(cid,'user',q.question,'[]'))
        c.execute('INSERT INTO messages(chat,role,content,sources) VALUES(?,?,?,?)',(cid,'assistant',answer,json.dumps(sources,ensure_ascii=False)))
    return {'chatid':cid,'answer':answer,'sources':sources,'provider':os.getenv('LLM_PROVIDER','offline'),'evidence_bundle':evidence,'retrieval':retrieval_info}
