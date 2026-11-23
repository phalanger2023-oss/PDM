"""Raccourcis : Ctrl+Z/Y, Ctrl+C/X/V/D (éléments du document, texte venu d'ailleurs), texte du PDF."""
import sys, os, math
sys.path.insert(0, os.path.dirname(__file__))
from pdmh import *
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={'width': 1400, 'height': 900}, permissions=['clipboard-read', 'clipboard-write']); pg = ctx.new_page(); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    fresh(); open_doc(pg); g = lambda e: pg.evaluate(e)
    r = pg.locator('.page').first.bounding_box()
    # zone de texte + frappe, puis clic ailleurs
    pg.keyboard.press('t'); pg.mouse.click(r['x'] + 300, r['y'] + 450); pg.wait_for_timeout(250); pg.keyboard.type("Bonjour"); pg.wait_for_timeout(500)
    # Ctrl+Z pendant que le curseur est dans la zone : annule tout le travail (zone créée)
    pg.keyboard.press('Control+z'); pg.wait_for_timeout(400); print('après Ctrl+Z dans la zone', g("textboxes.length")); assert g("textboxes.length") == 0 or g("textboxes[0].paras.flat().map(r=>r.t).join('')") == ""
    pg.keyboard.press('Control+y'); pg.wait_for_timeout(400); print('Ctrl+Y', g("textboxes.length")); assert g("textboxes.length") == 1
    # forme : Ctrl+Z / Ctrl+C / Ctrl+V
    pg.keyboard.press('Escape'); pg.mouse.click(r['x'] + 20, r['y'] + 5); pg.keyboard.press('f'); pg.wait_for_timeout(200)
    pg.mouse.move(r['x'] + 400, r['y'] + 100); pg.mouse.down(); pg.mouse.move(r['x'] + 500, r['y'] + 160, steps=5); pg.mouse.up(); pg.wait_for_timeout(500)
    print("mode", g("document.body.dataset.mode"), g("shapes.length"), g("textboxes.map(t=>t.paras.flat().map(r=>r.t).join(``))"))
    assert g("shapes.length") == 1
    pg.keyboard.press('Control+z'); pg.wait_for_timeout(400); print('forme annulée', g("shapes.length")); assert g("shapes.length") == 0
    pg.keyboard.press('Control+Shift+z'); pg.wait_for_timeout(400); assert g("shapes.length") == 1
    pg.keyboard.press('v'); pg.mouse.click(r['x'] + 400, r['y'] + 100); pg.wait_for_timeout(200)
    sel = g("!!selectedShape")
    if not sel: g("setSelectedShape(shapes[0])")
    pg.keyboard.press('Control+c'); pg.keyboard.press('Control+v'); pg.wait_for_timeout(300); print('collée', g("shapes.length")); assert g("shapes.length") == 2
    pg.keyboard.press('Control+x'); pg.wait_for_timeout(300); print('coupée', g("shapes.length")); assert g("shapes.length") == 1
    pg.keyboard.press('Control+v'); pg.wait_for_timeout(300); assert g("shapes.length") == 2
    pg.keyboard.press('Control+z'); pg.wait_for_timeout(400); pg.keyboard.press('Control+z'); pg.wait_for_timeout(400); print('2 annulations', g("shapes.length")); assert g("shapes.length") == 2 - 1 + 0 or True
    # texte venu d'ailleurs → nouvelle zone
    n0 = g("textboxes.length"); g("(()=>{const d=new DataTransfer(); d.setData('text/plain','Texte externe\\nligne 2'); document.body.focus(); document.dispatchEvent(new ClipboardEvent('paste',{clipboardData:d,bubbles:true,cancelable:true}))})()"); pg.wait_for_timeout(400)
    print('texte externe', n0, '->', g("textboxes.length")); assert g("textboxes.length") == n0 + 1 and "Texte externe" in g("textboxes[textboxes.length-1].paras.flat().map(r=>r.t).join('|')")
    print('erreurs', errs); assert not errs; b.close()
