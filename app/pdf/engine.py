"""Local OCR adapters. No user PDFs or images are transmitted to a service."""
import json,os,subprocess,threading,queue
from pathlib import Path

class WindowsOCR:
    identity='windows-zh-Hans-CN-v1'
    def __init__(self):
        script=Path(__file__).with_name('winocr.ps1')
        exe=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
        self.process=subprocess.Popen([str(exe),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(script)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8',bufsize=1)
        self.queue=queue.Queue()
        threading.Thread(target=self._read,daemon=True).start()
    def _read(self):
        for line in self.process.stdout:self.queue.put(line)
        self.queue.put(None)
    def recognize(self,image_path):
        self.process.stdin.write(json.dumps({'path':str(Path(image_path).resolve())},ensure_ascii=True)+'\n');self.process.stdin.flush()
        try:line=self.queue.get(timeout=90)
        except queue.Empty:
            self.close();raise RuntimeError('Windows OCR 单页超时')
        if not line:raise RuntimeError('Windows OCR 无法启动，请检查简体中文 OCR 语言包')
        result=json.loads(line)
        if not result['ok']:raise RuntimeError(result.get('error','OCR 失败'))
        return result
    def close(self):
        if self.process.poll() is None:self.process.terminate()

class RapidOCR:
    identity='rapidocr-onnxruntime-v1'
    def __init__(self):
        from rapidocr_onnxruntime import RapidOCR as Engine
        self.engine=Engine()
    def recognize(self,image_path):
        result,_=self.engine(str(image_path))
        return {'ok':True,'text':'\n'.join(r[1] for r in result or []),'confidence':[r[2] for r in result or []],'engine':self.identity}
    def close(self):pass

def get_engine():
    name=os.getenv('OCR_ENGINE','windows')
    if name=='windows':return WindowsOCR()
    if name=='rapidocr':return RapidOCR()
    raise ValueError('未知 OCR_ENGINE')
