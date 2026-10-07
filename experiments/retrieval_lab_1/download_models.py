"""Download pinned public weights only; no remote inference or executable code."""
import urllib.request,json,hashlib,time,concurrent.futures
from pathlib import Path
LAB=Path(__file__).resolve().parent
SPECS=[('e5-base','Xenova/multilingual-e5-base','intfloat/multilingual-e5-base','mit','onnx/model_quantized.onnx'),('bge-m3','Xenova/bge-m3','BAAI/bge-m3','mit','onnx/model_quantized.onnx'),('qwen-embedding','onnx-community/Qwen3-Embedding-0.6B-ONNX','Qwen/Qwen3-Embedding-0.6B','apache-2.0','onnx/model_quantized.onnx'),('bge-reranker','onnx-community/bge-reranker-v2-m3-ONNX','BAAI/bge-reranker-v2-m3','apache-2.0','onnx/model_quantized.onnx'),('qwen-reranker','onnx-community/Qwen3-Reranker-0.6B-ONNX','Qwen/Qwen3-Reranker-0.6B','apache-2.0','onnx/model_quantized.onnx')]
def fetch(spec):
 name,repo,upstream,license,weight=spec;folder=LAB/'models'/name;folder.mkdir(parents=True,exist_ok=True)
 locked=None
 if (folder/'manifest.json').exists():
  prior=json.loads((folder/'manifest.json').read_text(encoding='utf8'))
  if prior.get('source')==repo:locked=prior.get('revision')
 elif (LAB/'model_manifest.json').exists():
  prior=next((m for m in json.loads((LAB/'model_manifest.json').read_text(encoding='utf8'))['models'] if m['name']==name and m['source']==repo),{})
  locked=prior.get('revision')
 url='https://huggingface.co/api/models/'+repo+('/revision/'+locked if locked else '')+'?blobs=true'
 info=json.load(urllib.request.urlopen(url,timeout=60));rev=info['sha'];entries={x['rfilename']:x for x in info['siblings']}
 if locked and rev!=locked:raise ValueError('Pinned revision mismatch')
 m={'name':name,'source':repo,'source_url':'https://huggingface.co/'+repo,'revision':rev,'upstream':upstream,'license':license,'license_basis':'upstream license; third-party converter, not official weights','quantization':'dynamic INT8 ONNX; third-party conversion','weight':weight,'files':{},'started_at':time.time()}
 try:
  for file in [weight,'tokenizer.json','config.json','README.md']:
   if file not in entries:continue
   meta=entries[file];target=folder/file;target.parent.mkdir(parents=True,exist_ok=True);expected=meta.get('lfs',{}).get('sha256')
   if not target.exists() or target.stat().st_size!=meta['size']:
    url=f'https://huggingface.co/{repo}/resolve/{rev}/{file}?download=true';temp=target.with_suffix(target.suffix+'.part');done=0;last=time.monotonic()
    for attempt in range(3):
     try:
      with urllib.request.urlopen(url,timeout=90) as response,temp.open('wb') as f:
       while True:
        b=response.read(1024*1024)
        if not b:break
        f.write(b);done+=len(b)
        if time.monotonic()-last>30:print(name,file,round(done/1e6),'MB',flush=True);last=time.monotonic()
      temp.replace(target);break
     except Exception:
      if attempt==2:raise
      done=0;time.sleep(1)
   h=hashlib.sha256()
   with target.open('rb') as f:
    for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
   actual=h.hexdigest()
   if target.stat().st_size!=meta['size'] or expected and expected!=actual:raise ValueError('SHA256/size mismatch '+file)
   m['files'][file]={'bytes':target.stat().st_size,'sha256':actual,'hub_sha256':expected}
  m['status']='downloaded_verified';m['disk_bytes']=sum(x['bytes'] for x in m['files'].values());m['finished_at']=time.time()
 except Exception as e:m['status']='failed';m['error']=str(e)
 (folder/'manifest.json').write_text(json.dumps(m,indent=2),encoding='utf8');print(name,m['status'],flush=True);return m
if __name__=='__main__':
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:res=list(pool.map(fetch,SPECS))
 (LAB/'model_manifest.json').write_text(json.dumps({'models':res,'remote_inference':False},indent=2),encoding='utf8')
