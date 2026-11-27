import sys; sys.path.insert(0,'tests')
from pdmh import *
import urllib.request
try: urllib.request.urlopen(urllib.request.Request(B+'/api/docs/Multi.pdf/project', method='DELETE'))
except Exception: pass
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={'width':1200,'height':1100}); errs=[]; pg.on('pageerror',lambda e:errs.append(str(e)))
    open_doc(pg,'Multi.pdf'); pg.evaluate("window.scrollTo(0,0)"); pg.wait_for_timeout(1000)
    pg.evaluate("document.querySelector('input[value=highlight]').click()")
    def spans(pi):
        return pg.evaluate("(i)=>[...pages[i].textLayer.querySelectorAll('span')].map(s=>{const r=s.getBoundingClientRect();return [Math.round(r.left),Math.round(r.top),Math.round(r.right),Math.round(r.bottom),s.textContent.slice(0,12)]})",pi)
    s0=spans(0); print(len(s0), s0[:3])
    # 1) une ligne
    a=s0[0]; pg.mouse.move(a[0]+30,(a[1]+a[3])/2); pg.mouse.down(); pg.mouse.move(a[0]+200,(a[1]+a[3])/2,steps=5); pg.mouse.up(); pg.wait_for_timeout(300)
    print('1 ligne', pg.evaluate("highlights.map(h=>[h.page,h.rects.length])")); 
    # 2) plusieurs lignes
    a=s0[2]; c=s0[5]; pg.mouse.move(a[0]+20,(a[1]+a[3])/2); pg.mouse.down(); pg.mouse.move(c[0]+150,(c[1]+c[3])/2,steps=8); pg.mouse.up(); pg.wait_for_timeout(300)
    print('multi-lignes', pg.evaluate("highlights.map(h=>[h.page,h.rects.length])"))
    # 3) sur deux pages
    pg.evaluate("window.scrollTo(0, pages[0].div.offsetTop + 480)"); pg.wait_for_timeout(900)
    s0=spans(0); s1=spans(1); vis=lambda s:[x for x in s if 0<x[1]<1080]; print(pg.evaluate("[scrollY,pages[1].div.offsetTop,pages[0].div.offsetHeight]"))
    print(len(vis(s0)),len(vis(s1)))
    v0=vis(s0)[-1]; v1=vis(s1)[0]
    print('visibles',v0,v1)
    pg.mouse.move(v0[0]+20,(v0[1]+v0[3])/2); pg.mouse.down(); pg.mouse.move(v1[0]+200,(v1[1]+v1[3])/2,steps=10); pg.mouse.up(); pg.wait_for_timeout(300)
    hl=pg.evaluate("highlights.map(h=>[h.page,h.rects.length,h.rects.map(r=>r.map(Math.round))])"); print('2 pages',hl)
    # rects: aucune ne dépasse la page / pas de rect géant
    bad=pg.evaluate("highlights.flatMap(h=>h.rects.filter(r=>(r[2]-r[0])>pages[0].div.clientWidth/SCALE+1||(r[3]-r[1])>60))")
    print('rects anormaux',bad)
    # recouvrements
    ov=pg.evaluate("""highlights.map(h=>{let n=0;for(let i=0;i<h.rects.length;i++)for(let j=i+1;j<h.rects.length;j++){const a=h.rects[i],b=h.rects[j];const w=Math.min(a[2],b[2])-Math.max(a[0],b[0]),hh=Math.min(a[3],b[3])-Math.max(a[1],b[1]);if(w>1&&hh>2)n++}return n})""")
    print('rects qui se recouvrent',ov)
    # couleur
    print('couleur',pg.evaluate("highlights.map(h=>h.color)"))
    # annuler
    n=pg.evaluate("highlights.length"); pg.keyboard.press('Control+z'); pg.wait_for_timeout(400); print('undo',n,pg.evaluate("highlights.length"))
    print('erreurs',errs)
