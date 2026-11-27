import sys; sys.path.insert(0,'tests')
from pdmh import *
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={'width':1200,'height':800}); fresh(); open_doc(pg)
    errs=[]; pg.on('pageerror',lambda e:errs.append(str(e)))
    pg.evaluate("window.scrollTo(0,0)")
    pg.evaluate("document.querySelector('input[value=shape]').click()"); pg.click('[data-kind=line]')
    r=pg.locator('.page').first.bounding_box()
    # deux clics
    pg.mouse.click(r['x']+100,r['y']+200); pg.wait_for_timeout(150)
    pg.mouse.move(r['x']+200,r['y']+250,steps=3); pg.mouse.move(r['x']+300,r['y']+400,steps=3)
    print('en attente', pg.evaluate("!!pendingLine"), pg.evaluate("shapes.length"))
    pg.mouse.click(r['x']+300,r['y']+400); pg.wait_for_timeout(200)
    s=pg.evaluate("shapes.map(s=>[s.kind,Math.round(s.x0),Math.round(s.y0),Math.round(s.x1),Math.round(s.y1)])"); print(s)
    assert len(s)==1 and s[0][0]=='line' and abs(s[0][3]-s[0][1])>80 and not pg.evaluate("!!pendingLine")
    # Échap annule
    pg.mouse.click(r['x']+400,r['y']+200); pg.wait_for_timeout(100); pg.keyboard.press('Escape'); pg.wait_for_timeout(100)
    assert pg.evaluate("shapes.length")==1 and not pg.evaluate("!!pendingLine")
    # le glisser fonctionne toujours (flèche)
    pg.keyboard.press('Escape'); pg.evaluate("document.querySelector('input[value=shape]').click()"); pg.wait_for_timeout(150); pg.click('[data-kind=arrow]')
    pg.mouse.move(r['x']+100,r['y']+500); pg.mouse.down(); pg.mouse.move(r['x']+300,r['y']+560,steps=4); pg.mouse.up(); pg.wait_for_timeout(200)
    assert pg.evaluate("shapes.length")==2 and not pg.evaluate("!!pendingLine")
    # annuler / rétablir
    pg.keyboard.press('Escape'); pg.keyboard.press('Control+z'); pg.wait_for_timeout(300); n1=pg.evaluate("shapes.length")
    pg.keyboard.press('Control+y'); pg.wait_for_timeout(300); n2=pg.evaluate("shapes.length"); print('undo/redo',n1,n2)
    assert n1==1 and n2==2
    print('erreurs',errs); assert not errs; print("OK")
