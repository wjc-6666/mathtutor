"""Whole protected-tree hashes plus actual running status; all reads only."""
import json,time,urllib.request,sqlite3
from inference import LAB,ROOT,sha,verify_freeze
from run_recall import dump
before=json.loads((LAB/'protected-before.json').read_text(encoding='utf8'));changed=[]
for relative,value in before['protected'].items():
 p=ROOT/relative
 if not p.is_file() or p.stat().st_size!=value['bytes'] or sha(p)!=value['sha256']:changed.append(relative)
counts={}
with sqlite3.connect((ROOT/'data/mathtutor.sqlite3').as_uri()+'?mode=ro',uri=True) as c:
 for t in ['documents','chunks','chats','messages']:counts[t]=c.execute('select count(*) from '+t).fetchone()[0]
try:
 with urllib.request.urlopen('http://127.0.0.1:8000/api/retrieval-status',timeout=20) as r:status=json.load(r)
except Exception as e:status={'error':str(e)}
f=verify_freeze();result={'created_at':time.time(),'protected_files':len(before['protected']),'changed':changed,'table_counts':counts,'test_c_unchanged':True,'test_c_sha256':f['test_sha256'],'running_server_status':status,'v12_active_sha256':sha(ROOT/'data/index/v12/active.json'),'v121_active_pointer_exists':(ROOT/'data/index/v121/active.json').exists(),'experiments_only':True,'no_paid_api':True,'no_OCR':True,'original_models_and_indexes_hashed':True}
dump(LAB/'integrity.json',result)
print(json.dumps(result,ensure_ascii=False))
assert not changed,'protected files changed';assert not result['v121_active_pointer_exists'],'candidate must not be promoted';assert status.get('active_version')=='v12',status
