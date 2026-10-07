from pathlib import Path
import urllib.request, hashlib, json, time

root=Path(__file__).resolve().parents[1]
folder=root/'data/models/e5-small-int8'
folder.mkdir(parents=True,exist_ok=True)
revision='761b726dd34fb83930e26aab4e9ac3899aa1fa78'
files={'onnx/model_quantized.onnx':118308185,'tokenizer.json':17082730,'config.json':658,'tokenizer_config.json':443}
manifest={'repository':'Xenova/multilingual-e5-small','revision':revision,'base_model':'intfloat/multilingual-e5-small','base_license':'MIT','files':{}}
for name,size in files.items():
    target=folder/name;target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists() or target.stat().st_size!=size:
        request=urllib.request.Request(f'https://huggingface.co/Xenova/multilingual-e5-small/resolve/{revision}/{name}',headers={'User-Agent':'MathTutor/1.2'})
        partial=target.with_suffix(target.suffix+'.partial')
        with urllib.request.urlopen(request,timeout=120) as response,partial.open('wb') as out:
            while block:=response.read(1024*1024):out.write(block)
        if partial.stat().st_size!=size:raise RuntimeError(f'Unexpected size: {name}')
        partial.replace(target)
    manifest['files'][name]={'bytes':size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
    print('ready',name,size,flush=True)
(folder/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
