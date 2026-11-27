import sys; sys.path.insert(0,'tests')
from pdmh import *
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={'width':1000,'height':800}); fresh(); open_doc(pg)
    pg.evaluate("setZoom(3)"); pg.wait_for_timeout(1500)
    pg.evaluate("window.scrollTo(900,400)"); pg.wait_for_timeout(300)
    r=pg.locator('.page').first.bounding_box(); s0=pg.evaluate('[scrollX,scrollY]'); print('départ',s0)
    pg.keyboard.press('t'); pg.mouse.click(300,300); pg.wait_for_timeout(300); print('après clic',pg.evaluate('[scrollX,scrollY]'))
    pg.keyboard.type("Bonjour le monde et encore du texte"); pg.wait_for_timeout(300); print('après frappe',pg.evaluate('[scrollX,scrollY]'))
    pg.evaluate('window.scrollTo(300,400)'); pg.wait_for_timeout(200)
    pg.keyboard.press('Control+a'); sx=pg.evaluate("[scrollX,scrollY]")
    for how in ('btn','key'):
        if how=='btn': pg.click('[data-cmd=underline]')
        else: pg.keyboard.press('Control+u')
        pg.wait_for_timeout(500)
        now=pg.evaluate("[scrollX,scrollY]"); print(how,sx,now)
        assert abs(now[0]-sx[0])<3 and abs(now[1]-sx[1])<3, "la vue a bougé"
    print("OK")
