"""Ctrl+Z depuis un champ du panneau, zone de texte centrée sur le clic, deux lignes en haut."""
import sys; sys.path.insert(0, __import__('os').path.dirname(__file__))
from pdmh import *
ST = "[textboxes.length, textboxes[0]&&textboxes[0].size, undoIdx, undoStack.length]"
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={'width': 1300, 'height': 800}); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    fresh(); open_doc(pg)
    h = pg.evaluate("document.querySelector('.topbar').getBoundingClientRect().height"); print('hauteur barre', h); assert h < 100
    pg.evaluate("document.querySelector('input[value=text]').click()")
    bb = pg.locator('.page').first.bounding_box(); y = bb['y'] + 300
    pg.mouse.click(bb['x']+150, y); pg.wait_for_timeout(300); pg.keyboard.type('Bonjour'); pg.wait_for_timeout(600)
    r = pg.evaluate("(()=>{const b=document.querySelector('.tb').getBoundingClientRect();return [b.left,b.top+b.height/2]})()")
    assert abs(r[0]-(bb['x']+150)) < 3 and abs(r[1]-y) < 3, r
    pg.fill('#fSize', '30'); pg.wait_for_timeout(600)
    s0 = pg.evaluate(ST); print('avant', s0); assert s0[1] == 30
    pg.keyboard.press('Control+z'); pg.wait_for_timeout(500)
    s1 = pg.evaluate(ST); print('après ctrl+z', s1); assert s1[1] == 14 and s1[2] == s0[2]-1 and s1[3] == s0[3]
    pg.keyboard.press('Control+y'); pg.wait_for_timeout(500)
    s2 = pg.evaluate(ST); print('après ctrl+y', s2); assert s2[1] == 30
    print(errs); assert not errs
print('OK')
