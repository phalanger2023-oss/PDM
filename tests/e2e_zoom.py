"""Zoom fluide (transformation pendant le geste) et barre du haut immobile quand on défile à gauche / droite sur un document zoomé."""
import sys
sys.path.insert(0, __import__('os').path.dirname(__file__))
from pdmh import *
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={'width': 1000, 'height': 800}); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    open_doc(pg)
    s0 = pg.evaluate("SCALE")
    pg.click('#zoomIn'); pg.wait_for_timeout(60)
    tr = pg.evaluate("document.getElementById('viewer').style.transform"); print('pendant le geste:', tr); assert tr.startswith('scale(')
    pg.wait_for_timeout(1200)
    assert pg.evaluate("document.getElementById('viewer').style.transform") == '' and pg.evaluate("SCALE") > s0, 'rendu net après le geste'
    for _ in range(4): pg.click('#zoomIn'); pg.wait_for_timeout(300)
    pg.wait_for_timeout(1500); print('zoom', pg.evaluate("SCALE"))
    sw = pg.evaluate("document.documentElement.scrollWidth"); print('largeur défilable', sw); assert sw > 1100
    pg.evaluate("window.scrollTo(400, 300)"); pg.wait_for_timeout(200)
    tb = pg.evaluate("document.querySelector('.topbar').getBoundingClientRect().left"); print('barre du haut left =', tb); assert abs(tb) < 1
    pg.evaluate("window.scrollTo(0, 300)"); pg.wait_for_timeout(200)
    first = pg.evaluate("document.querySelector('.page').getBoundingClientRect().left"); print('1re page left (scrollX=0) =', first); assert first >= -1
    # Ctrl + molette : transformation puis rendu net
    pg.mouse.move(500, 400); pg.keyboard.down('Control'); pg.mouse.wheel(0, -200); pg.keyboard.up('Control'); pg.wait_for_timeout(60)
    print('molette:', pg.evaluate("document.getElementById('viewer').style.transform")); pg.wait_for_timeout(1500)
    assert pg.evaluate("document.getElementById('viewer').style.transform") == ''
    print('erreurs', errs); assert not errs; b.close(); print('OK')
