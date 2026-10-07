"""CLI demo with disposable sample PDF, never alters user books."""
import os,subprocess,sys,tempfile
from pathlib import Path
from test_flow import pdf_bytes

with tempfile.TemporaryDirectory(prefix='mathtutor-demo-') as folder:
    root=Path(folder)
    (root/'books/analysis').mkdir(parents=True)
    (root/'books/algebra').mkdir()
    (root/'books/analysis/demo.pdf').write_bytes(pdf_bytes())
    environment=dict(os.environ,MATHTUTOR_ROOT=folder,LLM_PROVIDER='offline',EMBEDDING_PROVIDER='hash')
    for args in [['index'],['ask','Uniform convergence']]:
        subprocess.run([sys.executable,'-m','app.cli',*args],env=environment,check=True)
