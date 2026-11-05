"""Build the illustrated operator manual from actual platform screenshots."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, Flowable, KeepTogether, Preformatted
from reportlab.platypus.tableofcontents import TableOfContents

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'docs/manual/Nazar_Vision_Illustrated_Manual_Content.json'
SHOTS=ROOT/'output/playwright/user_manual'
OUTPUT=ROOT/'output/pdf/Nazar_Vision_Complete_Illustrated_User_Manual_v1.0.pdf'
W,H=595.276,841.89
M=42
CW=W-2*M
BLUE=colors.HexColor('#2563EB')
NAVY=colors.HexColor('#0B1F3A')
INK=colors.HexColor('#243B59')
MUTED=colors.HexColor('#61738B')
ICE=colors.HexColor('#EFF5FF')
LINE=colors.HexColor('#D8E4F4')

FONT_DIR=Path('C:/Windows/Fonts')
for name,filename in [('NV','segoeui.ttf'),('NVB','segoeuib.ttf'),('NVI','segoeuii.ttf'),('NVMono','consola.ttf')]:
    pdfmetrics.registerFont(TTFont(name,str(FONT_DIR/filename)))
pdfmetrics.registerFontFamily('NV',normal='NV',bold='NVB',italic='NVI',boldItalic='NVB')
STYLES={
 'kicker':ParagraphStyle('Kicker',fontName='NVB',fontSize=8,leading=11,textColor=BLUE,spaceAfter=7),
 'title':ParagraphStyle('TaskTitle',fontName='NVB',fontSize=22,leading=26,textColor=NAVY,spaceAfter=9),
 'intro':ParagraphStyle('Intro',fontName='NV',fontSize=10.5,leading=15,textColor=MUTED,spaceAfter=12),
 'body':ParagraphStyle('Body',fontName='NV',fontSize=10,leading=14.3,textColor=INK,spaceAfter=7),
 'small':ParagraphStyle('Small',fontName='NV',fontSize=8.1,leading=11.4,textColor=MUTED,spaceAfter=7),
 'table':ParagraphStyle('TableBody',fontName='NV',fontSize=9.1,leading=12.8,textColor=INK),
 'th':ParagraphStyle('TableHeader',fontName='NVB',fontSize=8.8,leading=12,textColor=BLUE),
 'code':ParagraphStyle('Code',fontName='NVMono',fontSize=8.1,leading=11.5,textColor=INK,spaceBefore=6,spaceAfter=9),
 'toc':ParagraphStyle('Contents',fontName='NV',fontSize=10,leading=14.5,textColor=INK,spaceBefore=4,leftIndent=0,rightIndent=18),
}


def rich(text):
    value=escape(str(text))
    value=re.sub(r'\*\*(.+?)\*\*',r'<b>\1</b>',value)
    value=re.sub(r'`(.+?)`',r'<font name="NVMono">\1</font>',value)
    return value.replace('\n','<br/>')


def para(text,style='body'):
    return Paragraph(rich(text),STYLES[style])


class Figure(Flowable):
    def __init__(self,path,max_height=260,pins=None,crop=None):
        super().__init__()
        self.path=path
        self.max_height=max_height
        self.pins=pins or []
        self.spaceAfter=7
        self.image=ImageReader(str(path))
        self.original_width,self.original_height=self.image.getSize()
        crop=crop or [0,0,1,1]
        self.crop=[crop[0]*self.original_width,crop[1]*self.original_height,crop[2]*self.original_width,crop[3]*self.original_height]
        self.iw,self.ih=self.crop[2]-self.crop[0],self.crop[3]-self.crop[1]

    def wrap(self,width,height):
        scale=min((width-12)/self.iw,self.max_height/self.ih)
        self.w,self.h=self.iw*scale,self.ih*scale
        self.width=width;self.height=self.h+12
        return self.width,self.height

    def draw(self):
        c=self.canv
        x=(self.width-self.w)/2
        c.setFillColor(colors.white);c.setStrokeColor(LINE)
        c.roundRect(x-5,1,self.w+10,self.h+10,5,fill=1,stroke=1)
        c.saveState();clip=c.beginPath();clip.rect(x,6,self.w,self.h);c.clipPath(clip,stroke=0,fill=0)
        scale=self.w/self.iw
        c.drawImage(self.image,x-self.crop[0]*scale,6-(self.original_height-self.crop[3])*scale,
                    width=self.original_width*scale,height=self.original_height*scale,mask='auto')
        c.restoreState()
        for pin in self.pins:
            px=x+pin['x']*self.w;py=6+(1-pin['y'])*self.h
            c.setFillColor(BLUE);c.setStrokeColor(colors.white);c.setLineWidth(1.5)
            c.circle(px,py,8,fill=1,stroke=1)
            c.setFillColor(colors.white);c.setFont('NVB',8.5)
            c.drawCentredString(px,py-3,str(pin['n']))


class Number(Flowable):
    def __init__(self,n):
        super().__init__();self.n=n;self.width=21;self.height=20
    def draw(self):
        self.canv.setFillColor(ICE);self.canv.circle(9,10,8.5,fill=1,stroke=0)
        self.canv.setFillColor(BLUE);self.canv.setFont('NVB',9)
        self.canv.drawCentredString(9,7,str(self.n))


def steps(items):
    rows=[[Number(i+1),para(text)] for i,text in enumerate(items)]
    table=Table(rows,colWidths=[27,CW-27],hAlign='LEFT')
    table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),
                              ('RIGHTPADDING',(0,0),(-1,-1),0),('TOPPADDING',(0,0),(-1,-1),2),('BOTTOMPADDING',(0,0),(-1,-1),3)]))
    return table


def grid(headers,rows,widths=None):
    data=[[para(text,'th') for text in headers]]+[[para(text,'table') for text in row] for row in rows]
    widths=widths or ([CW*.27,CW*.73] if len(headers)==2 else [CW/len(headers)]*len(headers))
    table=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT')
    table.spaceBefore=4;table.spaceAfter=10
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),ICE),('LINEBELOW',(0,0),(-1,0),.7,LINE),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F8FAFD')]),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
    return table


def note(text,kind='Check'):
    value=para('**'+kind+'**  '+text,'table')
    table=Table([[value]],colWidths=[CW])
    table.spaceBefore=8;table.spaceAfter=4
    background=colors.HexColor('#FFF5E6') if kind=='EXAMPLE ONLY' else ICE
    border=colors.HexColor('#EFC98E') if kind=='EXAMPLE ONLY' else LINE
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),background),('BOX',(0,0),(-1,-1),.5,border),
        ('LEFTPADDING',(0,0),(-1,-1),10),('RIGHTPADDING',(0,0),(-1,-1),10),('TOPPADDING',(0,0),(-1,-1),9),('BOTTOMPADDING',(0,0),(-1,-1),9)]))
    return table


class Manual(BaseDocTemplate):
    def __init__(self,path):
        super().__init__(str(path),pagesize=(W,H),leftMargin=M,rightMargin=M,topMargin=55,bottomMargin=43,
            title='Nazar Vision - Complete Illustrated User Manual',author='Nazar Vision project',
            subject='Step-by-step instructions for dataset management, annotation, training, evaluation, inference and reports')
        frame=Frame(M,43,CW,H-98,leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)
        self.addPageTemplates(PageTemplate(id='Manual',frames=frame,onPage=self.decorate))
        self.topic_pages={}

    def decorate(self,c,doc):
        if doc.page==1:return
        c.saveState();c.setStrokeColor(LINE);c.line(M,H-35,W-M,H-35)
        c.setFillColor(BLUE);c.setFont('NVB',8);c.drawString(M,H-24,'NAZAR VISION')
        c.setFillColor(MUTED);c.setFont('NV',7.7);c.drawRightString(W-M,H-24,'COMPLETE ILLUSTRATED USER MANUAL')
        c.setStrokeColor(LINE);c.line(M,31,W-M,31)
        c.setFont('NV',7.2);c.drawString(M,19,'Version 1.0 | 29 October 2026 | Local research platform')
        c.drawRightString(W-M,19,f'{doc.page}')
        c.restoreState()

    def afterFlowable(self,flowable):
        key=getattr(flowable,'_bookmark',None)
        if key:
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(flowable.getPlainText(),key,level=0,closed=False)
            self.notify('TOCEntry',(0,flowable.getPlainText(),self.page,key))
            self.topic_pages[key]=self.page


class Cover(Flowable):
    def __init__(self):super().__init__();self.width=CW;self.height=H-100
    def draw(self):
        c=self.canv
        c.setFillColor(NAVY);c.rect(-M,-45,W,H,fill=1,stroke=0)
        c.setFillColor(colors.HexColor('#60A5FA'));c.setFont('NVB',10)
        c.drawString(0,675,'NAZAR VISION / OPERATOR HANDBOOK')
        c.setFillColor(colors.white);c.setFont('NVB',35)
        c.drawString(0,613,'Everything you need')
        c.drawString(0,570,'to use the platform.')
        c.setFont('NV',13);c.setFillColor(colors.HexColor('#C6D9F5'))
        c.drawString(0,531,'A complete, illustrated, step-by-step user manual')
        c.drawString(0,510,'for your sea turtle hatchling project.')
        image=ImageReader(str(SHOTS/'01_overview.png'));iw,ih=image.getSize();width=CW;h=width*ih/iw
        c.setFillColor(colors.white);c.roundRect(-4,121,width+8,h+8,8,fill=1,stroke=0)
        c.drawImage(image,0,125,width=width,height=h,preserveAspectRatio=True)
        c.setFillColor(colors.HexColor('#93C5FD'));c.setFont('NVB',10)
        c.drawString(0,103,'UPLOAD  /  REVIEW  /  PREPARE  /  TRAIN  /  EVALUATE  /  IMPROVE')
        c.setFillColor(colors.white);c.setFont('NV',10)
        c.drawString(0,71,'Final International University | Software Engineering graduation project')
        c.setFillColor(colors.HexColor('#9CB5D6'));c.setFont('NV',9)
        c.drawString(0,47,'Version 1.0 - 29 October 2026')
        c.drawString(0,28,'Actual application screenshots. Recorded test examples are identified.')


def height_of(items,canvas):
    total=0
    for item in items:
        total+=item.wrapOn(canvas,CW,H-98)[1]+item.getSpaceBefore()+item.getSpaceAfter()
    return total


def main():
    content=json.loads(SOURCE.read_text(encoding='utf-8'))
    for part in content.get('parts',[]):
        content['topics'].extend(json.loads((SOURCE.parent/part).read_text(encoding='utf-8'))['topics'])
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    document=Manual(OUTPUT)
    story=[Cover(),PageBreak(),para('START HERE','kicker'),para('Find the task you need.','title'),
           para('Click an entry to jump to the instructions. PDF bookmarks provide the same task list.','intro')]
    toc=TableOfContents();toc.levelStyles=[STYLES['toc']];toc.dotsMinLevel=0
    story.extend([toc,PageBreak()])
    from reportlab.pdfgen.canvas import Canvas
    import io
    measuring=Canvas(io.BytesIO())
    figures=[]
    measured=[]
    for index,topic in enumerate(content['topics'],1):
        if index>1:story.append(PageBreak())
        title=para(f'{index:02d}. '+topic['title'],'title')
        title._bookmark=topic['id']
        items=[para(topic['section'].upper(),'kicker'),title,para(topic['intro'],'intro')]
        if topic.get('example'):
            items.append(note('Recorded software-test fixture or isolated demonstration. These numbers do not measure independent field accuracy.','EXAMPLE ONLY'))
        figure=None
        if topic.get('image'):
            figure=Figure(SHOTS/(topic['image']+'.png'),topic.get('image_height',250),topic.get('pins'),topic.get('crop'))
            items.append(figure)
            items.append(para(topic['caption'],'small'))
            figures.append({'topic':topic['id'],'file':topic['image']+'.png','caption':topic['caption']})
        for paragraph in topic.get('paragraphs',[]):items.append(para(paragraph))
        for link in topic.get('links',[]):
            items.append(Paragraph('<link href="'+escape(link['url'],{'"':'&quot;'})+'" color="#2563EB">'+escape(link['label'])+'</link>',STYLES['small']))
        if topic.get('code'):items.append(Preformatted(topic['code'],STYLES['code']))
        if topic.get('steps'):items.append(steps(topic['steps']))
        if topic.get('table'):items.append(grid(topic['table']['headers'],topic['table']['rows']))
        if topic.get('note'):items.append(note(topic['note'],topic.get('note_title','Check before continuing')))
        if topic.get('next'):items.append(para('**Next:** '+topic['next'],'small'))
        while figure and height_of(items,measuring)>H-100 and figure.max_height>140:
            figure.max_height-=10
        measured.append({'id':topic['id'],'estimated_height':round(height_of(items,measuring),1),'figure_max_height':figure.max_height if figure else None})
        story.extend(items)
    document.multiBuild(story)
    from pypdf import PdfReader
    reader=PdfReader(OUTPUT)
    audit={'generated_at':datetime.now(timezone.utc).isoformat(),'pdf':OUTPUT.relative_to(ROOT).as_posix(),
           'pages':len(reader.pages),'topics':len(content['topics']),'figures':len(figures),
           'topic_pages':document.topic_pages,'layout_estimates':measured,'screenshots':figures,
           'sha256':hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
           'all_pages_have_text':all(bool(page.extract_text().strip()) for page in reader.pages)}
    (OUTPUT.parent/'Nazar_Vision_User_Manual_Build_Manifest.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
    print(json.dumps({k:audit[k] for k in ('pdf','pages','topics','figures','all_pages_have_text')},indent=2))


if __name__=='__main__':main()
