import sys; sys.path.insert(0,'tests')
from pdmh import *
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={'width':1100,'height':800}); fresh(); open_doc(pg)
    pg.evaluate("window.scrollTo(0, 700)"); pg.wait_for_timeout(500)
    def probe(x,y):
        return pg.evaluate("""([x,y])=>{const pgs=[...document.querySelectorAll('.page')];for(const d of pgs){const r=d.getBoundingClientRect();if(y>=r.top&&y<=r.bottom)return [pgs.indexOf(d),(x-r.left)/r.width,(y-r.top)/r.height]}return null}""",[x,y])
    for (x,y,dy) in [(300,300,-1),(800,500,-0.5),(300,300,0.4)]:
        a=probe(x,y); pg.mouse.move(x,y)
        pg.keyboard.down('Control'); pg.mouse.wheel(0,dy*100); pg.keyboard.up('Control'); pg.wait_for_timeout(1200)
        c=probe(x,y); print(a,c, pg.evaluate("SCALE"))
        assert c and a[0]==c[0] and abs(a[1]-c[1])<0.02 and abs(a[2]-c[2])<0.02, "vue décalée"
    print("OK")
