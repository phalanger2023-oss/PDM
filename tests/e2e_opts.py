import sys; sys.path.insert(0,'tests')
from pdmh import *
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={'width':1300,'height':800}); errs=[]; pg.on('pageerror',lambda e:errs.append(str(e)))
    fresh(); open_doc(pg); pg.evaluate("window.scrollTo(0,0)")
    pg.keyboard.press('t'); pg.mouse.click(600,300); pg.wait_for_timeout(300); pg.keyboard.type("Salut"); pg.wait_for_timeout(300)
    vis=lambda: pg.evaluate("(()=>{const b=document.getElementById('formatbar');const r=b.getBoundingClientRect();return [getComputedStyle(b).display,Math.round(r.width),Math.round(document.getElementById('viewer').getBoundingClientRect().left)]})()")
    print('ouvert',vis()); pg.screenshot(path='/tmp/opts_on.png')
    txt=pg.evaluate("[...document.querySelectorAll('#formatbar *')].filter(e=>e.offsetParent&&e.children.length==0&&e.textContent.trim()&&!['OPTION','B','I','U','S'].includes(e.tagName)).map(e=>e.textContent.trim())"); print('textes visibles',txt)
    pg.click('#optsBtn'); pg.wait_for_timeout(300); print('masqué',vis()); assert vis()[0]=='none'; pg.screenshot(path='/tmp/opts_off.png')
    pg.reload(); pg.wait_for_selector('.page'); pg.wait_for_timeout(800); print('après rechargement',pg.evaluate("document.body.classList.contains('opts-off')")); assert pg.evaluate("document.body.classList.contains('opts-off')")
    pg.click('#optsBtn'); pg.wait_for_timeout(200); assert not pg.evaluate("document.body.classList.contains('opts-off')")
    print('erreurs',errs); assert not errs; print('OK')
