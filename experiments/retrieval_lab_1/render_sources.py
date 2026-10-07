import json,sqlite3
from pathlib import Path
import pypdfium2 as pdfium
from PIL import Image,ImageDraw,ImageFont
root=Path(r'C:\Users\王景初\Desktop\MathTutor');lab=root/'experiments/retrieval_lab_1';out=Path(__file__).parent/'lab1-pages';out.mkdir(exist_ok=True)
select={'高等':[154,169,175,225,231,248,266,320,332,366,508,552],'数学分析中的':[102,115,133,146,171,182,208,222,238,302,483],'裴礼文':[34,64,73,81,127,156]}
with sqlite3.connect((root/'data/mathtutor.sqlite3').as_uri()+'?mode=ro',uri=True) as c:docs=c.execute('select name,path,id from documents').fetchall()
font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',22);items=[]
for name,path,docid in docs:
 pages=next(ps for key,ps in select.items() if name.startswith(key));pdf=pdfium.PdfDocument(path)
 for page in pages:
  p=pdf[page-1];bitmap=p.render(scale=1.5);img=bitmap.to_pil().convert('RGB');img.thumbnail((1050,1460));canvas=Image.new('RGB',(1100,1520),'white');canvas.paste(img,((1100-img.width)//2,45));ImageDraw.Draw(canvas).text((12,6),name[:12]+f' PDF {page}',font=font,fill='black');items.append(canvas)
  canvas.save(out/f'{docid}-{page}.png');bitmap.close();p.close()
 pdf.close()
for start in range(0,len(items),4):
 canvas=Image.new('RGB',(2200,3040),'white')
 for j,img in enumerate(items[start:start+4]):canvas.paste(img,((j%2)*1100,(j//2)*1520))
 canvas.save(out/f'contact-{start//4+1}.png')
print(len(items),'pages',len(range(0,len(items),4)),'contact sheets')
