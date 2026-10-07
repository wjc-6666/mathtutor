"""Continue this authorized experiment after serialized dense stage finishes."""
import time,json,subprocess,sys
from pathlib import Path
LAB=Path(__file__).resolve().parent
while not all((LAB/'results_recall'/f'{n}-test_c.json').exists() for n in ['e5-small','e5-base','bge-m3','qwen-D1','qwen-D2']):time.sleep(20)
print('ALL DENSE RUNS COMPLETED; BEGIN FIXED POOL STAGE',flush=True)
r=subprocess.run([sys.executable,str(LAB/'run_stage2.py')],cwd=LAB)
print('STAGE2 EXIT',r.returncode,flush=True)
if r.returncode:sys.exit(r.returncode)
for script in ['measure_active.py','audit_sources.py','summarize.py','verify_safety.py']:
 r=subprocess.run([sys.executable,str(LAB/script)],cwd=LAB)
 if r.returncode:sys.exit(r.returncode)
print('PIPELINE COMPLETE',flush=True)
