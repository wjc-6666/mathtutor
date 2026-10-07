import io
import pytest
from pypdf import PdfReader,PdfWriter
from PIL import Image,ImageChops
from test_flow import env,pdf_bytes

@pytest.fixture
def document(env):
    root,client=env
    writer=PdfWriter()
    first=pdf_bytes();second=first.replace(b'Uniform convergence:',b'Second page marker: ')
    assert len(first)==len(second)
    for raw in [first,second]:writer.add_page(PdfReader(io.BytesIO(raw)).pages[0])
    output=io.BytesIO();writer.write(output);content=output.getvalue()
    response=client.post('/api/upload',data={'subject':'analysis'},files={'file':('pages.pdf',content,'application/pdf')})
    assert response.status_code==200,response.text
    return root,client,response.json()['id'],content

def test_original_pdf_inline_and_range(document):
    root,client,docid,content=document
    response=client.get(f'/api/documents/{docid}/pdf')
    assert response.status_code==200 and response.headers['content-type']=='application/pdf'
    assert response.headers['content-disposition'].startswith('inline')
    assert response.content==content
    partial=client.get(f'/api/documents/{docid}/pdf',headers={'Range':'bytes=0-31'})
    assert partial.status_code==206 and partial.content==content[:32]
    assert (root/'books/analysis/pages.pdf').read_bytes()==content

def test_missing_document(env):
    root,client=env
    for suffix in ['pdf','page/1']:
        response=client.get('/api/documents/not-a-document/'+suffix)
        assert response.status_code==404 and response.json()['detail']=='资料不存在'

def test_first_page_matches_original_and_second_differs(document,monkeypatch):
    root,client,docid,content=document
    import app.pdf.pipeline as pipeline
    def unexpected(*a,**k):pytest.fail('Viewing original pages must never OCR or index')
    monkeypatch.setattr(pipeline,'process_pdf',unexpected)
    import app.main as main
    monkeypatch.setattr(main,'index_file',unexpected)
    first=client.get(f'/api/documents/{docid}/page/1')
    second=client.get(f'/api/documents/{docid}/page/2')
    assert first.status_code==second.status_code==200
    assert first.headers['content-type']==second.headers['content-type']=='image/png'
    a=Image.open(io.BytesIO(first.content)).convert('RGB');b=Image.open(io.BytesIO(second.content)).convert('RGB')
    assert a.width>=1000 and ImageChops.difference(a,b).getbbox() is not None
    # Independent single-page fixture provides the page-one content oracle.
    import pypdfium2
    with pypdfium2.PdfDocument(pdf_bytes()) as original:
        page=original[0];bitmap=page.render(scale=2.5)
        try:expected=bitmap.to_pil().convert('RGB');assert ImageChops.difference(a,expected).getbbox() is None
        finally:bitmap.close();page.close()
    assert not (root/'data/page_preview').exists()
    assert (root/'books/analysis/pages.pdf').read_bytes()==content

def test_invalid_page_bounds_even_if_old_preview_exists(document):
    root,client,docid,content=document
    from app.database.store import connect
    with connect() as c:digest=c.execute('SELECT digest FROM documents WHERE id=?',(docid,)).fetchone()[0]
    old=root/'data/page_preview'/digest/'3.png';old.parent.mkdir(parents=True);old.write_bytes(b'old preview')
    for page in [0,-1,3]:assert client.get(f'/api/documents/{docid}/page/{page}').status_code==404
    assert old.read_bytes()==b'old preview'
    assert client.get(f'/api/documents/{docid}/page/not-an-integer').status_code==422

def test_missing_original_file(document):
    root,client,docid,content=document
    (root/'books/analysis/pages.pdf').unlink()
    for suffix in ['pdf','page/1']:
        response=client.get(f'/api/documents/{docid}/{suffix}')
        assert response.status_code==404 and response.json()['detail']=='原始 PDF 文件不存在'

def test_rejects_outside_paths_and_ignores_client_path(document):
    root,client,docid,content=document
    outside=root/'private.pdf';outside.write_bytes(b'private file')
    response=client.get(f'/api/documents/{docid}/pdf',params={'path':str(outside)})
    assert response.content==content
    from app.database.store import connect
    for path in [str(outside),'books/analysis/../../private.pdf']:
        with connect() as c:c.execute('UPDATE documents SET path=? WHERE id=?',(path,docid))
        for suffix in ['pdf','page/1']:
            response=client.get(f'/api/documents/{docid}/{suffix}')
            assert response.status_code==404 and b'private file' not in response.content

def test_rejects_non_pdf(document):
    root,client,docid,content=document
    notes=root/'books/analysis/notes.md';notes.write_text('plain notes',encoding='utf8')
    from app.database.store import connect
    with connect() as c:c.execute('UPDATE documents SET path=? WHERE id=?',(str(notes),docid))
    assert client.get(f'/api/documents/{docid}/pdf').status_code==400
