"""Serialize CPU benchmarks to avoid comparing contended model timings."""
import sys,subprocess,time,json
from pathlib import Path
LAB=Path(__file__).resolve().parent
for name in ['e5-small','e5-base','bge-m3','qwen-embedding']:
 if name=='e5-small':
  # Discard preliminary performance from a redundant-session adapter probe,
  # keeping its weights/rank outputs in the experiment archive.
  for file in ['vectors.npy','index.json']:
   p=LAB/'runs'/name/file;target=p.with_name('preliminary-'+file)
   if p.exists() and not target.exists():p.rename(target)
 print('START MODEL',name,flush=True)
 with (LAB/(name+'-run.log')).open('w',encoding='utf8') as log:
  run=subprocess.run([sys.executable,str(LAB/'run_recall.py'),name],stdout=log,stderr=subprocess.STDOUT,cwd=LAB,timeout=7500)
 print('END MODEL',name,'exit',run.returncode,flush=True)
 if run.returncode:print((LAB/(name+'-run.log')).read_text(encoding='utf8')[-1600:],flush=True)
