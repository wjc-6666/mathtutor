"""Fresh-process co-resident route startup; generic inputs, no benchmark scores."""
import sys,json,time,subprocess
import numpy as np
from inference import LAB,ONNX,memory,verify_freeze
from run_recall import dump

def child(name):
 verify_freeze();results=json.loads((LAB/'results.json').read_text(encoding='utf8'))
 if name in results['retrieval']:
  d=results['retrieval'][name];reranker=None
 else:d=results['reranking'][name];reranker=d['reranker']
 model=d.get('model') or results['retrieval'][d['retriever']]['model']
 start=time.perf_counter();dense=ONNX(model)
 vectors=np.load(LAB/'runs'/model/'vectors.npy')
 corpus=json.loads((LAB/'corpus.json').read_text(encoding='utf8'))
 extra=None
 if reranker=='current':
  from run_rerank import rules_adapter
  extra=rules_adapter(corpus)
 elif reranker:extra=ONNX(reranker)
 cold=time.perf_counter()-start;after_load=memory()
 text='A mathematical function is continuous when sufficiently close inputs produce close outputs. The theorem relates continuity, limits, sequences, and local properties. '*80
 # Full-budget generic input to expose route buffers while both models stay alive.
 dense.embed([text],query=True,instruction=verify_freeze()['qwen_instruction'] if d.get('retriever')=='qwen-D2' else None)
 if reranker and reranker!='current':extra.rerank('What is continuity?',[text]*(4 if reranker=='bge-reranker' else 1),verify_freeze()['qwen_instruction'])
 dump(LAB/'startup'/f'{name}.json',{'route':name,'cold_components_after_import_seconds':cold,'models_co_resident':True,'OS_file_cache_flushed':False,'scope':'model hash/tokenizer/ORT + index/corpus + current adapter or neural model; generic full-budget warm inputs; not web-server boot, not Test C query timing','after_load':after_load,'after_generic_warmup':memory()})

if __name__=='__main__':
 if len(sys.argv)>1:child(sys.argv[1])
 else:
  r=json.loads((LAB/'results.json').read_text(encoding='utf8'))
  for name in [*r['retrieval'],*r['reranking']]:
   print('STARTUP',name,flush=True)
   subprocess.run([sys.executable,__file__,name],check=True,timeout=180)
