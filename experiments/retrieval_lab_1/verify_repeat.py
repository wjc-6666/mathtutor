"""Fresh-process Test C replay, no index rebuild or relevance changes."""
import json,time,argparse
import numpy as np
from inference import LAB,ONNX,verify_freeze,sha,memory
from run_recall import dump
def run(name):
 policy=verify_freeze();e=ONNX(name);vectors=np.load(LAB/'runs'/name/'vectors.npy');corp=json.loads((LAB/'corpus.json').read_text(encoding='utf8'));questions=json.loads((LAB/'test_c.json').read_text(encoding='utf8'))['questions'];records=corp['records'];ids=np.array([r['id'] for r in records])
 variants=[name] if name!='qwen-embedding' else ['qwen-D1','qwen-D2'];results={}
 for variant in variants:
  prior=json.loads((LAB/'results_recall'/f'{variant}-test_c.json').read_text(encoding='utf8'));matches=[];differences=[]
  for q,c in zip(questions,prior['cases']):
   instruction=policy['qwen_instruction'] if variant=='qwen-D2' else None;v,_=e.embed([q['query']],query=True,instruction=instruction);actual=ids[np.argsort(-(vectors@v[0]),kind='stable')[:50]].tolist();expected=[r['id'] for r in c['top50']];matches.append(actual==expected)
   if actual!=expected:differences.append(q['id'])
  results[variant]={'queries':len(matches),'identical_top50':sum(matches),'differences':differences}
 dump(LAB/'repeat'/f'{name}.json',{'fresh_process':True,'test_sha256':sha(LAB/'test_c.json'),'results':results,'time':time.time(),**memory()});print(results,flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('name');run(p.parse_args().name)
