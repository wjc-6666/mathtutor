"""CPU-only, local verified ONNX adapters. No app configuration changes."""
import json,time,hashlib,threading,ctypes,os,sys
from pathlib import Path
import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer
LAB=Path(__file__).resolve().parent;ROOT=LAB.parents[1]
class Counters(ctypes.Structure):
 _fields_=[('cb',ctypes.c_ulong),('PageFaultCount',ctypes.c_ulong),('PeakWorkingSetSize',ctypes.c_size_t),('WorkingSetSize',ctypes.c_size_t),('QuotaPeakPagedPoolUsage',ctypes.c_size_t),('QuotaPagedPoolUsage',ctypes.c_size_t),('QuotaPeakNonPagedPoolUsage',ctypes.c_size_t),('QuotaNonPagedPoolUsage',ctypes.c_size_t),('PagefileUsage',ctypes.c_size_t),('PeakPagefileUsage',ctypes.c_size_t),('PrivateUsage',ctypes.c_size_t)]
def memory():
 c=Counters();c.cb=ctypes.sizeof(c)
 ctypes.windll.kernel32.GetCurrentProcess.restype=ctypes.c_void_p
 fn=ctypes.windll.psapi.GetProcessMemoryInfo;fn.argtypes=[ctypes.c_void_p,ctypes.POINTER(Counters),ctypes.c_ulong]
 if not fn(ctypes.windll.kernel32.GetCurrentProcess(),ctypes.byref(c),c.cb):raise ctypes.WinError()
 return {'rss_bytes':c.WorkingSetSize,'peak_rss_bytes':c.PeakWorkingSetSize,'private_bytes':c.PrivateUsage}
def cpu_time():
 t=os.times();return t.user+t.system
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
class ONNX:
 def __init__(self,name):
  start=time.perf_counter();self.name=name;self.folder=LAB/'models'/name
  if name=='e5-small':self.folder=ROOT/'data/models/e5-small-int8'
  self.manifest=json.loads((self.folder/'manifest.json').read_text(encoding='utf8'));weight=self.manifest.get('weight','onnx/model_quantized.onnx')
  for file in [weight,'tokenizer.json']:
   if sha(self.folder/file)!=self.manifest['files'][file]['sha256']:raise ValueError('model hash mismatch '+file)
  options=ort.SessionOptions();options.intra_op_num_threads=4;options.inter_op_num_threads=1
  options.enable_cpu_mem_arena=name=='e5-small'
  self.control=None
  if name=='e5-small':
   sys.path.insert(0,str(ROOT));from app.rag.local_dense import E5CPU
   self.control=E5CPU(self.folder);self.session=self.control.session
  else:self.session=ort.InferenceSession(str(self.folder/weight),sess_options=options,providers=['CPUExecutionProvider'])
  self.inputs=self.session.get_inputs();self.outputs=self.session.get_outputs()
  self.tokenizer=Tokenizer.from_file(str(self.folder/'tokenizer.json'))
  self.tokenizer.enable_truncation(max_length=384)
  config=json.loads((self.folder/'config.json').read_text(encoding='utf8'))
  self.pad=int(config.get('pad_token_id') or (151643 if name.startswith('qwen') else 0 if name.startswith('e5') else 1))
  self.tokenizer.enable_padding(pad_id=self.pad,pad_token='<|endoftext|>' if name.startswith('qwen') else '<pad>' if name.startswith('bge') else '[PAD]')
  self.config=config;self.cold_seconds=time.perf_counter()-start
 def inputs_for(self,encoded):
  ids=np.asarray([t.ids for t in encoded],dtype=np.int64);mask=np.asarray([t.attention_mask for t in encoded],dtype=np.int64)
  values={'input_ids':ids,'attention_mask':mask,'token_type_ids':np.asarray([t.type_ids for t in encoded],dtype=np.int64),'position_ids':np.maximum(np.cumsum(mask,axis=1)-1,0).astype(np.int64),'use_cache_branch':np.asarray([False],dtype=bool)}
  for x in self.inputs:
   if x.name not in values:
    if 'past' in x.name:
     shape=[ids.shape[0] if k==0 else 0 if k==2 else dim if isinstance(dim,int) else self.config.get('num_key_value_heads',8) if k==1 else self.config.get('head_dim',128) for k,dim in enumerate(x.shape)];values[x.name]=np.zeros(shape,dtype=np.float32)
    else:raise ValueError('Unsupported ONNX input '+str((x.name,x.shape,x.type)))
  return {x.name:values[x.name] for x in self.inputs},mask
 def embed(self,texts,query=False,instruction=None):
  strings=[('query: ' if query else 'passage: ')+t if self.name.startswith('e5') else 'Instruct: '+instruction+'\nQuery:'+t if query and instruction else t for t in texts]
  encoded=self.tokenizer.encode_batch(strings);values,mask=self.inputs_for(encoded)
  if self.control:
   return self.control.embed(texts,query=query),{'tokens':[sum(t.attention_mask) for t in encoded],'truncated':[sum(t.attention_mask)>=384 for t in encoded]}
  candidates=[x.name for x in self.outputs if x.name in ['last_hidden_state','sentence_embedding','sentence_embeddings','token_embeddings','dense_vecs']]
  output=self.session.run(candidates[:1] if candidates else [self.outputs[0].name],values)[0]
  if output.ndim==3:
   if self.name.startswith('qwen'):vectors=output[np.arange(len(output)),np.max(np.where(mask,np.arange(mask.shape[1]),-1),axis=1)]
   elif self.name=='bge-m3':vectors=output[:,0]
   else:vectors=(output*mask[:,:,None]).sum(1)/np.maximum(mask.sum(1)[:,None],1)
  else:vectors=output
  vectors=vectors.astype(np.float32);vectors/=np.maximum(np.linalg.norm(vectors,axis=1,keepdims=True),1e-12)
  if vectors.ndim!=2 or not np.isfinite(vectors).all():raise ValueError('Invalid embedding values/shape')
  return vectors,{'tokens':[sum(t.attention_mask) for t in encoded],'truncated':[sum(t.attention_mask)>=384 for t in encoded]}
 def rerank(self,query,passages,instruction):
  if self.name=='bge-reranker':
   encoded=self.tokenizer.encode_batch([(query,p) for p in passages]);values,mask=self.inputs_for(encoded)
   scores=self.session.run([self.outputs[0].name],values)[0].reshape(-1)
  else:
   prefix='<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and the Instruct provided. Note that the answer can only be "yes" or "no".<|im_end|>\n<|im_start|>user\n'
   suffix='<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n'
   # Reserve the complete answer suffix. Truncate document only, never suffix.
   saved=self.tokenizer.truncation;self.tokenizer.no_truncation();pre=self.tokenizer.encode(prefix,add_special_tokens=False).ids;post=self.tokenizer.encode(suffix,add_special_tokens=False).ids
   sequences=[]
   for p in passages:
    core=self.tokenizer.encode(f'<Instruct>: {instruction}\n<Query>: {query}\n<Document>: {p}',add_special_tokens=False).ids
    sequences.append(pre+core[:384-len(pre)-len(post)]+post)
   self.tokenizer.enable_truncation(max_length=384)
   length=max(map(len,sequences));ids=np.array([[self.pad]*(length-len(s))+s for s in sequences],dtype=np.int64);mask=(ids!=self.pad).astype(np.int64)
   values={'input_ids':ids,'attention_mask':mask,'position_ids':np.maximum(np.cumsum(mask,axis=1)-1,0).astype(np.int64)}
   for x in self.inputs:
    if x.name not in values:
     if 'past' in x.name:values[x.name]=np.zeros((len(sequences),self.config.get('num_key_value_heads',8),0,self.config.get('head_dim',128)),dtype=np.float32)
     else:raise ValueError('unsupported reranker input '+x.name)
   logits=self.session.run([self.outputs[0].name],{x.name:values[x.name] for x in self.inputs})[0]
   if logits.ndim==3:logits=logits[:,-1]
   yes=self.tokenizer.token_to_id('yes');no=self.tokenizer.token_to_id('no');scores=logits[:,yes]-logits[:,no]
  if not np.isfinite(scores).all():raise ValueError('Invalid rerank logits')
  return scores.tolist()
def verify_freeze():
 f=json.loads((LAB/'freeze.json').read_text(encoding='utf8'))
 assert sha(LAB/'test_c.json')==f['test_sha256'],'Test C mutated'
 assert sha(LAB/'corpus.json')==f['passages_sha256'],'corpus mutated'
 return f
