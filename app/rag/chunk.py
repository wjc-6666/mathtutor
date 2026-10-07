import re
HEADING=re.compile(r'^\s*(?:[★☆*女費]\s*)?(定义|定理|引理|推论|例题|例)\s*(\d+(?:[.．]\d+)*)(?:\s|[:：]|(?=[\u4e00-\u9fff]))',re.M)
CHAPTER=re.compile(r'^\s*(?:\d{1,4}\s+)?(第\s*[一二三四五六七八九十百零\d]+\s*章\s*[^\n]{0,35})',re.M)
SECTION=re.compile(r'^\s*[★☆*]?\s*((?:第[一二三四五六七八九十\d]+节|§\s*\d+\s*[.．·，,]\s*\d+)\s+[^\n]{2,40})$',re.M)
TYPES={'定义':'definition','定理':'theorem','引理':'lemma','推论':'corollary','例题':'example','例':'example'}
def chunks(page,limit=1400,overlap=200):
    if limit<=overlap or overlap<0:raise ValueError('Chunk 长度必须大于 overlap')
    text=page['text'].strip()
    if not text:return []
    structure=page.get('structure_text',text);chapter=page.get('chapter');section=page.get('section')
    found=CHAPTER.search(structure)
    if found:chapter=found[1].strip()
    found=SECTION.search(structure)
    if found:section=found[1].strip()
    boundaries=list(HEADING.finditer(text));blocks=[]
    if boundaries:
        if boundaries[0].start():blocks.append((text[:boundaries[0].start()],'text',None))
        for i,m in enumerate(boundaries):
            end=boundaries[i+1].start() if i+1<len(boundaries) else len(text)
            blocks.append((text[m.start():end],TYPES[m[1]],m[1]+m[2].replace('．','.')))
    else:blocks=[(text,'proof' if re.match(r'^\s*证明',text) else 'text',None)]
    result=[]
    for block,kind,label in blocks:
        current=''
        for unit in re.split(r'\n\s*\n',block):
            unit=unit.strip()
            if not unit:continue
            if current and len(current)+len(unit)+2>limit:
                result.append((current,kind,label));current=current[-overlap:] if overlap else ''
            if len(unit)>limit:
                if current:result.append((current,kind,label));current=''
                while len(unit)>limit:
                    window=unit[:limit];cut=max(window.rfind('\n'),window.rfind('。'))
                    cut=cut+1 if cut>limit//2 else limit
                    result.append((unit[:cut],kind,label));unit=unit[max(1,cut-overlap):]
            current=(current+'\n\n'+unit).strip()
        if current:result.append((current,kind,label))
    n=page.get('pdf_page',page.get('page'))
    return [dict(page,text=t,chapter=chapter,section=section,subsection=None,content_type=kind,label=label,pdf_page_start=n,pdf_page_end=n,printed_page=page.get('printed_page')) for t,kind,label in result]
