"""Mode Dessiner (même famille que Surligner), gomme, poignées haut / bas / rond d'angle d'une zone de texte."""
import sys, math
sys.path.insert(0, __import__('os').path.dirname(__file__))
from pdmh import *
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={'width': 1400, 'height': 900}); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    fresh(); open_doc(pg)
    r = pg.locator('.page').first.bounding_box()
    # --- dessin : le bouton est à côté du surlignage
    order = pg.evaluate("[...document.querySelectorAll('input[name=mode]')].map(i=>i.value)"); print(order); assert order[1:3] == ['highlight', 'draw']
    pg.keyboard.press('d'); pg.wait_for_timeout(200)
    assert pg.evaluate("document.body.dataset.mode") == 'draw' and not pg.locator('#drawbar').is_hidden()
    pg.fill('#dWidth', '5'); pg.evaluate("document.querySelector('#dSw .sw').click()")
    for k in range(2):  # deux traits d'affilée
        x, y = r['x'] + 150, r['y'] + 200 + k * 80
        pg.mouse.move(x, y); pg.mouse.down()
        for i in range(1, 25): pg.mouse.move(x + i * 5, y + math.sin(i / 3) * 18)
        pg.mouse.up(); pg.wait_for_timeout(150)
    print('traits', pg.evaluate("shapes.map(s=>[s.kind,s.width,s.stroke])")); assert pg.evaluate("shapes.length") == 2 and pg.evaluate("shapes[0].width") == 5
    # --- gomme
    pg.click("#dEraser"); pt = pg.evaluate("(()=>{const h=document.querySelector('.hit[data-pen]');const q=h.getPointAtLength(h.getTotalLength()/2);const m=h.getScreenCTM();return [q.x*m.a+m.e,q.y*m.d+m.f]})()"); print(pt); pg.mouse.click(pt[0], pt[1]); pg.wait_for_timeout(300)
    print('après gomme', pg.evaluate("shapes.length")); assert pg.evaluate("shapes.length") == 1
    pg.click('#dEraser')
    # --- zone de texte : haut, bas, rond
    pg.keyboard.press('t'); pg.mouse.click(r['x'] + 300, r['y'] + 450); pg.wait_for_timeout(250); pg.keyboard.type("Titre"); pg.wait_for_timeout(200)
    g = lambda e: pg.evaluate(e)
    y1_0, size0, x1_0 = g("textboxes[0].y1"), g("textboxes[0].size"), g("textboxes[0].x1")
    t = pg.locator('.tb.selected .tb-top').bounding_box()
    pg.mouse.move(t['x'] + 12, t['y'] + 3); pg.mouse.down(); pg.mouse.move(t['x'] + 12, t['y'] - 50, steps=6); pg.mouse.up(); pg.wait_for_timeout(250)
    print('haut: taille', size0, '->', g("textboxes[0].size"), '| bas fixe', round(y1_0, 1), round(g("textboxes[0].y1"), 1)); assert g("textboxes[0].size") > size0 and abs(g("textboxes[0].y1") - y1_0) < 1.5
    size1, y0_1 = g("textboxes[0].size"), g("textboxes[0].y0")
    bt = pg.locator('.tb.selected .tb-bottom').bounding_box()
    pg.mouse.move(bt['x'] + 12, bt['y'] + 3); pg.mouse.down(); pg.mouse.move(bt['x'] + 12, bt['y'] + 40, steps=6); pg.mouse.up(); pg.wait_for_timeout(250)
    print('bas: taille', size1, '->', g("textboxes[0].size"), '| haut fixe', round(y0_1, 1), round(g("textboxes[0].y0"), 1)); assert g("textboxes[0].size") > size1 and abs(g("textboxes[0].y0") - y0_1) < 1.5
    size2, x1_2, x0_2 = g("textboxes[0].size"), g("textboxes[0].x1"), g("textboxes[0].x0")
    c = pg.locator('.tb.selected .tb-corner').bounding_box()
    pg.mouse.move(c['x'] + 8, c['y'] + 8); pg.mouse.down(); pg.mouse.move(c['x'] + 68, c['y'] + 40, steps=6); pg.mouse.up(); pg.wait_for_timeout(250)
    print('rond: taille', size2, '->', g("textboxes[0].size"), 'largeur', round(x1_2 - x0_2), '->', round(g("textboxes[0].x1") - g("textboxes[0].x0")))
    assert g("textboxes[0].size") > size2 and g("textboxes[0].x1") > x1_2 and abs(g("textboxes[0].x0") - x0_2) < 0.5
    print('erreurs', errs); assert not errs; b.close()
