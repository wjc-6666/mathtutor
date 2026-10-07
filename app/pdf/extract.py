from pathlib import Path
from pypdf import PdfReader

def pages(path: Path):
    if path.suffix.lower()=='.pdf':
        from app import config
        from app.pdf.pipeline import process_pdf,cached_pages
        folder,_=process_pdf(path,config.DATA/'ocr')
        yield from cached_pages(folder)
    elif path.suffix.lower() in {'.txt','.md'}:
        yield {'text':path.read_text(encoding='utf-8-sig'),'page':None,'title':path.stem}
    else: raise ValueError('仅支持 PDF、UTF-8 TXT、Markdown')
