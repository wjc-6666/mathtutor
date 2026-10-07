"""Pinned, local-only quantized multilingual E5; never falls back to hash."""
from pathlib import Path
import json, threading, time,hashlib

class E5CPU:
    def __init__(self,folder):
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer
        self.folder=Path(folder)
        self.manifest=json.loads((self.folder/'manifest.json').read_text(encoding='utf8'))
        for name in ['onnx/model_quantized.onnx','tokenizer.json']:
            path=self.folder/name;expected=self.manifest['files'][name]
            if path.stat().st_size!=expected['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest()!=expected['sha256']:
                raise ValueError('本地语义模型文件校验失败：'+name)
        self.identity='e5-int8:'+self.manifest['revision']+':mean-pool:384tokens:v1'
        options=ort.SessionOptions();options.intra_op_num_threads=4;options.inter_op_num_threads=1
        self.session=ort.InferenceSession(str(self.folder/'onnx/model_quantized.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
        self.tokenizer=Tokenizer.from_file(str(self.folder/'tokenizer.json'))
        self.tokenizer.enable_truncation(max_length=384);self.tokenizer.enable_padding(pad_id=0,pad_token='[PAD]')
        self.lock=threading.Lock();self.np=np

    def embed(self,texts,query=False,batch_size=8,progress=None):
        np=self.np;result=[]
        with self.lock:
            for start in range(0,len(texts),batch_size):
                encoded=self.tokenizer.encode_batch([('query: ' if query else 'passage: ')+str(t) for t in texts[start:start+batch_size]])
                values={'input_ids':np.array([t.ids for t in encoded],dtype=np.int64),
                        'attention_mask':np.array([t.attention_mask for t in encoded],dtype=np.int64),
                        'token_type_ids':np.array([t.type_ids for t in encoded],dtype=np.int64)}
                inputs={x.name:values[x.name] for x in self.session.get_inputs()}
                output=self.session.run(None,inputs)[0]
                if output.ndim==3:
                    mask=values['attention_mask'][:,:,None];vectors=(output*mask).sum(1)/np.maximum(mask.sum(1),1)
                else:vectors=output
                vectors=vectors/np.maximum(np.linalg.norm(vectors,axis=1,keepdims=True),1e-12)
                result.extend(vectors.astype(np.float32))
                if progress:progress(min(start+batch_size,len(texts)),len(texts))
        return np.asarray(result,dtype=np.float32)
