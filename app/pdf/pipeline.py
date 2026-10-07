"""Page-level OCR cache; resumable and never rewrites the source PDF."""
import hashlib,json,os,re,time,threading,tempfile
from pathlib import Path
from collections import Counter
from app.pdf.engine import get_engine

PIPELINE='ocr-page-v3'
_locks={};_guard=threading.Lock()
def file_hash(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def quality(text):
    s=re.sub(r'\s','',text)
    bad=sum(c in '\ufffd\x00' or '\ue000'<=c<='\uf8ff' for c in s)
    useful=sum(c.isalnum() or '\u4e00'<=c<='\u9fff' for c in s)
    ok=len(s)>=40 and useful/max(1,len(s))>=.5 and bad/max(1,len(s))<.03
    return {'usable':ok,'characters':len(s),'bad_ratio':round(bad/max(1,len(s)),3)}
def clean(text):
    # Raw OCR is retained separately. Never strip mathematical punctuation/superscripts.
    text=text.replace('\x00','').replace('\r','')
    text=re.sub(r'([A-Za-z])-\n([a-z])',r'\1\2',text)
    for _ in range(4):text=re.sub(r'([\u4e00-\u9fff]) +(?=[\u4e00-\u9fff])',r'\1',text)
    # Only normalize a recognizable numbered heading, not arbitrary decimal formulae.
    text=re.sub(r'((?:例题|例|定理|定义|引理|推论)\s*)(\d+(?:\s*[.．·，,]\s*\d+)+)',lambda m:m[1]+re.sub(r'\s|[．·，,]',lambda n:'.' if not n[0].isspace() else '',m[2]),text)
    return '\n'.join(line.rstrip() for line in text.splitlines()).strip()
def atomic(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(path)
def cache_dir(path,cache_root,digest=None):
    digest=digest or file_hash(path)
    signature=hashlib.sha256((PIPELINE+os.getenv('OCR_ENGINE','windows')+os.getenv('OCR_SCALE','2')).encode()).hexdigest()[:12]
    return Path(cache_root)/digest/signature
def load(path):
    try:return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError,ValueError):return None
def book_title(path):
    name=Path(path).stem
    from app import config
    mapping=load(config.ROOT/'book_titles.json') or {}
    if Path(path).name in mapping:return mapping[Path(path).name]
    if '裴礼文' in name or '典型问题与方法' in name:
        return '数学分析中的典型问题与方法（习题解答）' if '解答' in name else '数学分析中的典型问题与方法'
    if '高等代数' in name and ('谢启鸿' in name or '复旦' in name):return '高等代数（第四版，复旦大学学习指导书）'
    return name
def inspect_pdf(path,folder=None):
    from pypdf import PdfReader
    reader=PdfReader(path);rows=[]
    for n,p in enumerate(reader.pages,1):
        try:text=p.extract_text() or '';q=quality(text);error=None
        except Exception as e:text='';q=quality('');error=str(e)
        rows.append({'pdf_page':n,'text':text,'quality':q,'needs_ocr':not q['usable'],'error':error})
    info={'source_file':Path(path).name,'book_name':book_title(path),'total_pages':len(rows),'needs_ocr_pages':[r['pdf_page'] for r in rows if r['needs_ocr']], 'text_layer_pages':sum(not r['needs_ocr'] for r in rows), 'text_layer':'可用' if all(not r['needs_ocr'] for r in rows) else '部分可用' if any(not r['needs_ocr'] for r in rows) else '不可用','checked_pages':len(rows),'sample_pages':sorted({1,max(1,len(rows)//4),max(1,len(rows)//2),max(1,len(rows)*3//4),len(rows)})}
    if folder:atomic(Path(folder)/'inspection.json',info)
    return rows,info
def render_page(document,number,path):
    page=document[number-1]
    try:
        bitmap=page.render(scale=float(os.getenv('OCR_SCALE','2')))
        try:
            image=bitmap.to_pil();image.thumbnail((2400,2400));image.save(path)
        finally:bitmap.close()
    finally:page.close()
def process_pdf(path,cache_root,progress=None,retry_failed=True,engine_factory=get_engine):
    path=Path(path);digest=file_hash(path);folder=cache_dir(path,cache_root,digest)
    with _guard:lock=_locks.setdefault(str(folder),threading.Lock())
    with lock:
        folder.mkdir(parents=True,exist_ok=True)
        previous=load(folder/'manifest.json')
        if previous and previous.get('status')=='completed':return folder,previous
        rows,info=inspect_pdf(path,folder);engine=None;document=None;done=0;reused=0;failed=[]
        state=dict(info,file_hash=digest,pipeline=PIPELINE,engine=os.getenv('OCR_ENGINE','windows'),engine_version=None,status='running',started_at=time.time(),updated_at=time.time(),completed_pages=0,ocr_success=0,failed_pages=[],cache_reused=0)
        atomic(folder/'manifest.json',state)
        try:
            for row in rows:
                n=row['pdf_page'];pagefile=folder/f'{n:05d}.json';cached=load(pagefile)
                if cached and (cached['success'] or not retry_failed):result=cached;reused+=1
                else:
                    result={'pdf_page':n,'printed_page':None,'source_file':path.name,'book_name':info['book_name'],'success':False,'method':'ocr' if row['needs_ocr'] else 'text','raw_text':'','text':'','error':None,'timestamp':time.time()}
                    try:
                        if row['needs_ocr']:
                            if engine is None:engine=engine_factory()
                            if document is None:
                                import pypdfium2
                                document=pypdfium2.PdfDocument(str(path))
                            with tempfile.TemporaryDirectory(prefix='mathtutor-ocr-') as scratch:
                                imagepath=Path(scratch)/'page.png';render_page(document,n,imagepath)
                                recognized=engine.recognize(imagepath)
                            raw=recognized['text'];result['engine']=recognized.get('engine',getattr(engine,'identity','unknown'));result['engine_version']=recognized.get('version');state['engine_version']=result['engine_version'] or state['engine_version']
                        else:raw=row['text']
                        result.update(success=True,raw_text=raw,text=clean(raw),quality=quality(clean(raw)))
                    except Exception as e:
                        result['error']=str(e)
                        if engine:engine.close();engine=None
                    atomic(pagefile,result)
                done+=1
                if not result['success']:failed.append(n)
                elif result['method']=='ocr':state['ocr_success']+=1
                state.update(completed_pages=done,failed_pages=failed,cache_reused=reused,updated_at=time.time(),current_page=n,percent=round(done/max(1,len(rows))*100,1))
                atomic(folder/'manifest.json',state)
                if progress:progress(dict(state))
        finally:
            if engine:engine.close()
            if document:document.close()
        state.update(status='completed' if not failed else 'partial',updated_at=time.time())
        atomic(folder/'manifest.json',state)
        return folder,state
def cached_pages(folder):
    manifest=load(Path(folder)/'manifest.json')
    if not manifest:return []
    rows=[load(Path(folder)/f'{n:05d}.json') for n in range(1,manifest['total_pages']+1)]
    rows=[r for r in rows if r and r['success']]
    rows=[dict(r,text=clean(r['raw_text'])) for r in rows]
    # Conservative repeated edge-line removal, with raw text always retained.
    counts=Counter()
    for r in rows:
        lines=r['text'].splitlines()
        counts.update(set(lines[:2]+lines[-2:]))
    repeated={line for line,n in counts.items() if n>=max(5,len(rows)*.35) and len(line)>6 and not re.search(r'[=∑∫Σ<>]',line)}
    result=[]
    for r in rows:
        lines=r['text'].splitlines();kept=[]
        for i,line in enumerate(lines):
            edge=i<2 or i>=len(lines)-2
            if edge and line in repeated:continue
            kept.append(line)
        result.append(dict(r,text='\n'.join(kept),page=r['pdf_page'],title=r['book_name'],structure_text=r['text'],chapter=None,section=None))
    return result
