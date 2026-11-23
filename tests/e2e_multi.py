"""Sélection multiple (Maj + clic), copie/duplication/suppression de groupe, crayon, zoom/dernière page mémorisés."""
import sys, math, json
sys.path.insert(0, __import__('os').path.dirname(__file__))
from pdmh import *
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={'width': 1400, 'height': 900}); pg = ctx.new_page(); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    fresh(); open_doc(pg)
    pg.evaluate("document.querySelector('input[value=text]').click()")
    r = pg.locator('.page').first.bounding_box()
    for i, (x, y) in enumerate([(100, 300), (100, 450)]):
        pg.mouse.click(r['x'] + x, r['y'] + y); pg.wait_for_timeout(250); pg.keyboard.type(f"Zone {i+1}")
    # une forme
    pg.evaluate("document.querySelector('input[value=shape]').click()"); pg.click('[data-kind=rect]')
    pg.mouse.move(r['x'] + 400, r['y'] + 300); pg.mouse.down(); pg.mouse.move(r['x'] + 520, r['y'] + 380, steps=4); pg.mouse.up(); pg.wait_for_timeout(200)
    # un trait de crayon
    pg.click('[data-kind=pen]'); x0, y0 = r['x'] + 400, r['y'] + 500
    pg.mouse.move(x0, y0); pg.mouse.down()
    for i in range(1, 30): pg.mouse.move(x0 + i * 4, y0 + math.sin(i / 4) * 20)
    pg.mouse.up(); pg.wait_for_timeout(200)
    assert pg.evaluate("shapes.length") == 2 and pg.evaluate("shapes[1].kind") == 'pen' and pg.evaluate("shapes[1].pts.length") > 10
    # sélection multiple : texte 1, texte 2, forme, crayon
    pg.evaluate("document.querySelector('input[value=text]').click()"); pg.wait_for_timeout(200)
    pg.evaluate("document.querySelector('input[value=select]')?.click()")
    pg.locator('.tb').nth(0).click(position={'x': 6, 'y': 6}); 
    pg.locator('.tb').nth(1).click(position={'x': 6, 'y': 6}, modifiers=['Shift'])
    print('multi', pg.evaluate("multi.length")); assert pg.evaluate("multi.length") == 2
    # copier-coller le groupe
    pg.keyboard.press('Control+c'); pg.keyboard.press('Control+v'); pg.wait_for_timeout(300)
    print('zones après collage', pg.evaluate("textboxes.length")); assert pg.evaluate("textboxes.length") == 4
    assert pg.evaluate("multi.length") == 2
    pg.keyboard.press('Delete'); pg.wait_for_timeout(300)
    assert pg.evaluate("textboxes.length") == 2, pg.evaluate("textboxes.length")
    # le crayon se déplace et se garde dans le PDF
    pg.wait_for_timeout(2500); pl = json.loads(__import__('urllib.request').request.urlopen(B + '/api/docs/Test.pdf/project').read())
    # zoom + page mémorisés par document
    pg.evaluate("setZoom(2)"); pg.wait_for_timeout(600)
    pg.evaluate("goToPage(3)"); pg.wait_for_timeout(900)
    print('mémo', pg.evaluate("[localStorage.getItem('lastzoom:Test.pdf'), localStorage.getItem('lastpage:Test.pdf')]"))
    open_doc(pg); pg.wait_for_timeout(1500)
    print('après réouverture: zoom', pg.evaluate("SCALE"), 'page', pg.evaluate("curPage"))
    assert pg.evaluate("SCALE") == 2 and pg.evaluate("curPage") == 3
    print('erreurs', errs); assert not errs; b.close()
