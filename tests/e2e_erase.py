"""Mode Supprimer : un clic efface zone de texte, forme, note, surlignage ; Ctrl+Z annule ; panneau compact."""
import sys; sys.path.insert(0, __import__('os').path.dirname(__file__))
from pdmh import *
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={'width': 1300, 'height': 800}); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    fresh(); open_doc(pg)
    bb = pg.locator('.page').first.bounding_box()
    pg.evaluate("document.querySelector('input[name=mode][value=text]').click()")
    pg.mouse.click(bb['x']+100, bb['y']+300); pg.wait_for_timeout(400); pg.keyboard.type('Bonjour'); pg.wait_for_timeout(300)
    w = pg.evaluate("document.querySelector('.ctxbar:not([hidden]):not(#findbar)').getBoundingClientRect().width"); print('panneau', w); assert w <= 190
    pg.evaluate("document.querySelector('input[name=mode][value=note]').click()")
    pg.mouse.click(bb['x']+400, bb['y']+500); pg.fill('.dlg-input','ma note'); pg.keyboard.press('Control+Enter'); pg.wait_for_timeout(500)
    pg.evaluate("document.querySelector('input[name=mode][value=shape]').click()")
    pg.mouse.move(bb['x']+200, bb['y']+600); pg.mouse.down(); pg.mouse.move(bb['x']+320, bb['y']+680, steps=6); pg.mouse.up(); pg.wait_for_timeout(500)
    print('avant:', pg.evaluate("[textboxes.length, notes.length, shapes.length]")); assert pg.evaluate("textboxes.length>=1 && notes.length==1 && shapes.length>=1")
    pg.keyboard.press('Escape')
    pg.click('label.seg:has(input[value=erase])'); pg.wait_for_timeout(300); assert pg.evaluate("currentMode()") == 'erase'
    pg.locator('.note').first.click(); pg.wait_for_timeout(300)
    pg.locator('.tb').first.click(); pg.wait_for_timeout(300)
    hb = pg.locator('.shape-layer .hit').first.bounding_box(); pg.mouse.click(hb['x']+1, hb['y']+hb['height']/2); pg.wait_for_timeout(400)
    print('après:', pg.evaluate("[textboxes.length, notes.length, shapes.length]")); assert pg.evaluate("textboxes.length==0 && notes.length==0 && shapes.length==0")
    pg.evaluate("document.querySelector('input[name=mode][value=select]').click()")
    pg.keyboard.press('Control+z'); pg.wait_for_timeout(300)
    print('après annuler:', pg.evaluate("[textboxes.length, notes.length, shapes.length]"))
    pg.keyboard.press('x'); pg.wait_for_timeout(200); print('touche x ->', pg.evaluate("currentMode()")); assert pg.evaluate("currentMode()") == 'erase'
    pg.screenshot(path='/tmp/erase.png')
    print('erreurs', errs); assert not errs
print('OK')
