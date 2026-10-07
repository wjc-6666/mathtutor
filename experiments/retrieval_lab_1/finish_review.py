"""Finish local measurements/tests after the authorized model pipeline."""
import sys,subprocess,time,json
from pathlib import Path
LAB=Path(__file__).resolve().parent;ROOT=LAB.parents[1]
while not ((LAB/'integrity.json').exists() and (LAB/'results.json').exists()):time.sleep(10)
integrity=json.loads((LAB/'integrity.json').read_text(encoding='utf8'))
assert not integrity['changed'] and integrity['running_server_status']['active_version']=='v12'
for script in ['measure_startup.py','finalize_diagnostics.py']:
 print('POST RUN',script,flush=True)
 subprocess.run([sys.executable,str(LAB/script)],cwd=LAB,check=True)
print('RUN FULL PYTEST',flush=True)
with (LAB/'pytest-final.txt').open('w',encoding='utf8') as f:
 r=subprocess.run([sys.executable,'-m','pytest','-q',r'--basetemp=.\data\pytest-temp'],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
print((LAB/'pytest-final.txt').read_text(encoding='utf8'),flush=True)
if r.returncode:sys.exit(r.returncode)
subprocess.run([sys.executable,str(LAB/'verify_safety.py')],cwd=LAB,check=True)
print('POST RUN VALIDATION COMPLETE',flush=True)
