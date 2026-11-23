"""Test navigateur (Playwright) des zones de texte. Lancer : PDM sur le port 5055 avec un PDF « Test.pdf »."""
import sys, json
sys.path.insert(0, __import__('os').path.dirname(__file__))
from pdmh import *

with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={'width': 1400, 'height': 900}); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    fresh(); open_doc(pg)
    pg.click('input[name=mode][value=text]', force=True) if pg.locator('input[name=mode][value=text]').count() else None
    pg.evaluate("document.querySelector('input[value=text]').click()")
    pg.wait_for_timeout(200)
    page1 = pg.locator('.page').first.bounding_box()
    # 1. création par simple clic
    pg.mouse.click(page1['x'] + 100, page1['y'] + 300); pg.wait_for_timeout(300)
    ed = pg.locator('.tb .ed').first
    assert ed.evaluate("e => e === document.activeElement"), "éditeur pas actif"
    assert ed.evaluate("e => e.spellcheck") is True
    h0 = pg.evaluate("textboxes[0].y1 - textboxes[0].y0")
    pg.keyboard.type("Bonjour")
    for i in range(3):
        pg.keyboard.press('Enter'); pg.keyboard.type(f"ligne {i+2}")
    pg.wait_for_timeout(200)
    h1 = pg.evaluate("textboxes[0].y1 - textboxes[0].y0")
    print('hauteur', round(h0, 1), '->', round(h1, 1)); assert h1 > h0 * 2.5
    assert pg.evaluate("JSON.stringify(textboxes[0].paras).includes('ligne 4')")
    # 2. interligne
    pg.fill('#fLh', '2'); pg.wait_for_timeout(200)
    h2 = pg.evaluate("textboxes[0].y1 - textboxes[0].y0"); print('interligne 2 ->', round(h2, 1)); assert h2 > h1 * 1.4
    assert pg.evaluate("textboxes[0].lh") == 2
    # 3. police
    pg.select_option('#fFont', 'carl'); pg.wait_for_timeout(300)
    assert pg.evaluate("textboxes[0].font") == 'carl'
    assert 'Carlito' in pg.evaluate("document.querySelector('.tb .ed').style.fontFamily")
    # 4. barre latérale droite : largeur
    w0 = pg.evaluate("textboxes[0].x1 - textboxes[0].x0")
    r = pg.locator('.tb.selected .tb-edge.r').bounding_box()
    pg.mouse.move(r['x'] + 3, r['y'] + 10); pg.mouse.down(); pg.mouse.move(r['x'] + 103, r['y'] + 10, steps=5); pg.mouse.up()
    w1 = pg.evaluate("textboxes[0].x1 - textboxes[0].x0"); print('largeur', round(w0), '->', round(w1)); assert w1 > w0 + 40
    # 5. poignée du haut : taille du texte
    s0 = pg.evaluate("textboxes[0].size")
    t = pg.locator('.tb.selected .tb-top').bounding_box()
    pg.mouse.move(t['x'] + 10, t['y'] + 3); pg.mouse.down(); pg.mouse.move(t['x'] + 10, t['y'] - 60, steps=5); pg.mouse.up()
    s1 = pg.evaluate("textboxes[0].size"); print('taille', s0, '->', s1); assert s1 > s0
    # 6. forme + calques
    pg.evaluate("document.querySelector('input[value=shape]').click()")
    pg.mouse.move(page1['x'] + 90, page1['y'] + 280); pg.mouse.down(); pg.mouse.move(page1['x'] + 300, page1['y'] + 420, steps=4); pg.mouse.up()
    pg.wait_for_timeout(200)
    assert pg.evaluate("shapes.length") == 1
    zs, zt = pg.evaluate("shapes[0].z"), pg.evaluate("textboxes[0].z"); print('z forme/texte', zs, zt); assert zs > zt
    assert pg.locator('.shape-layer').count() >= 2
    pg.click('#shapebar [data-layer=back]'); pg.wait_for_timeout(200)
    assert pg.evaluate("shapes[0].z") < pg.evaluate("textboxes[0].z")
    pl = pg.evaluate("payload()")
    assert pl['shapes'][0]['z'] < pl['textboxes'][0]['z']
    # copie / duplication de la forme
    pg.click('#sDup'); pg.wait_for_timeout(200)
    assert pg.evaluate("shapes.length") == 2 and pg.evaluate("shapes[1].x0 > shapes[0].x0")
    # 7. texte : dupliquer puis zone vide qu'on quitte = supprimée
    pg.evaluate("document.querySelector('input[value=text]').click()")
    pg.mouse.click(page1['x'] + 400, page1['y'] + 600); pg.wait_for_timeout(200)
    n = pg.evaluate("textboxes.length"); print('zones avec la vide', n)
    pg.mouse.click(page1['x'] + 150, page1['y'] + 750); pg.wait_for_timeout(300)  # clic ailleurs => crée une autre, la vide disparaît
    n2 = pg.evaluate("textboxes.filter(t => !plainOf(t.paras).trim()).length"); print('vides', n2); assert n2 <= 1
    # 8. zoom ctrl+molette
    z0 = pg.evaluate("SCALE")
    pg.mouse.move(700, 500); pg.keyboard.down('Control'); pg.mouse.wheel(0, -300); pg.keyboard.up('Control'); pg.wait_for_timeout(900)
    z1 = pg.evaluate("SCALE"); print('zoom', z0, '->', z1); assert z1 > z0
    print('erreurs page:', errs); assert not errs
    pg.screenshot(path='/tmp/e2e1.png'); b.close()
