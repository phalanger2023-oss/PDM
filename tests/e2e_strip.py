"""Barre d'outils verticale : une icône par ligne, à gauche, sans chevaucher les pages ni les panneaux."""
import sys; sys.path.insert(0, __import__('os').path.dirname(__file__))
from pdmh import *
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={'width': 1300, 'height': 800}); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    fresh(); open_doc(pg)
    r = pg.evaluate("[...document.querySelectorAll('.modes .seg span')].map(e=>{const b=e.getBoundingClientRect();return [Math.round(b.left),Math.round(b.top)]})")
    print(r); assert len({x for x,_ in r}) == 1 and len({y for _,y in r}) == len(r) and r[0][0] < 44, 'une icône par ligne'
    def clear():
        s = pg.evaluate("document.querySelector('.modes').getBoundingClientRect().right"); v = pg.evaluate("document.querySelector('.page').getBoundingClientRect().left")
        return s, v
    print('barre/page', clear()); assert clear()[1] >= clear()[0]
    pg.click('#thumbsBtn'); pg.wait_for_timeout(500)
    t = pg.evaluate("document.getElementById('thumbs').getBoundingClientRect().left"); print('miniatures left', t); assert t >= 43
    pg.click('label.seg:has(input[value=text])'); pg.wait_for_timeout(400)
    c = pg.evaluate("document.querySelector('.ctxbar:not([hidden]):not(#findbar)').getBoundingClientRect()"); th = pg.evaluate("document.getElementById('thumbs').getBoundingClientRect().right")
    print('options left', c['left'], 'miniatures right', th); assert c['left'] >= th - 1
    pg.click('label.seg:has(input[value=erase])'); assert pg.evaluate("currentMode()") == 'erase'
    pg.screenshot(path='/tmp/strip.png'); print(errs); assert not errs
print('OK')
