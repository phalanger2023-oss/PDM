"""Calques sur la barre du haut, barre latérale compacte, pages épinglées, numéro de première page, sauvegarde."""
import sys, json, urllib.request
sys.path.insert(0, __import__('os').path.dirname(__file__))
from pdmh import *
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={'width': 1200, 'height': 800}); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    fresh(); urllib.request.urlopen(urllib.request.Request(B+'/api/docs/Test.pdf/meta', data=json.dumps({'pins': [], 'firstPage': 1}).encode(), headers={'Content-Type': 'application/json'}, method='PUT'))
    open_doc(pg)
    # calques : sur la barre du haut, grisés sans sélection
    box = pg.evaluate("(()=>{const l=document.getElementById('layerline').getBoundingClientRect(),t=document.querySelector('.topbar').getBoundingClientRect();return [l.top>=t.top,l.bottom<=t.bottom+1,l.height>0]})()")
    print('calques dans la barre:', box); assert all(box)
    assert pg.evaluate("[...document.querySelectorAll('#layerline [data-layer]')].every(b=>b.disabled)")
    # barre latérale
    pg.click('#thumbsBtn'); pg.wait_for_timeout(600)
    w = pg.evaluate("document.getElementById('thumbs').getBoundingClientRect().width"); print('largeur latérale', w); assert w <= 120
    n = pg.evaluate("document.querySelectorAll('.thumb').length"); print('pages', n)
    # épingle
    pg.hover('.thumbw >> nth=0'); pg.click('.thumbpin >> nth=0'); pg.wait_for_timeout(500)
    assert pg.evaluate("document.querySelectorAll('.pinchip').length") == 1
    # numéro de première page
    pg.once('dialog', lambda d: d.accept('101')); pg.click('#firstPageBtn'); pg.wait_for_timeout(500)
    assert pg.evaluate("document.querySelector('.thumb span').textContent") == '101', pg.evaluate("document.querySelector('.thumb span').textContent")
    assert pg.input_value('#pageNum') == '101'
    if n > 1:
        pg.fill('#pageNum', '102'); pg.press('#pageNum', 'Enter'); pg.wait_for_timeout(600)
        assert pg.evaluate("curPage") == 2, pg.evaluate("curPage")
    # persistance (rechargement)
    pg.reload(); pg.wait_for_selector('.page'); pg.wait_for_timeout(1200)
    print('après rechargement:', pg.evaluate("[docMeta.firstPage, docMeta.pins.join()]")); assert pg.evaluate("docMeta.firstPage") == 101 and pg.evaluate("docMeta.pins.length") == 1
    assert pg.evaluate("document.querySelectorAll('.pinchip').length") == 1
    # calques actifs avec une forme / zone de texte sélectionnée
    pg.evaluate("document.querySelector('input[name=mode][value=text]').click()")
    pg.evaluate('window.scrollTo(0,0)'); pg.wait_for_timeout(300); bb = pg.locator('.page').first.bounding_box()
    pg.mouse.click(bb['x']+100, bb['y']+300); pg.wait_for_timeout(400)
    pg.keyboard.type('A'); pg.keyboard.press('Escape'); pg.mouse.click(bb['x']+100, bb['y']+500); pg.wait_for_timeout(400)
    pg.keyboard.type('B'); pg.wait_for_timeout(300)
    print('zones:', pg.evaluate("textboxes.length"), 'sélection:', pg.evaluate("!!layerItem()"))
    assert pg.evaluate("textboxes.length") >= 1 and pg.evaluate("!!layerItem()")
    assert pg.evaluate("[...document.querySelectorAll('#layerline [data-layer]')].every(b=>!b.disabled)"), 'calques actifs'
    print('sel', pg.evaluate('selected && selected.z')); z0 = pg.evaluate("textboxes.map(t=>t.z)"); pg.click('#layerline [data-layer=back]'); z1 = pg.evaluate("textboxes.map(t=>t.z)")
    print('z avant/après', z0, z1); assert z0 != z1
    pg.screenshot(path='/tmp/sidebar.png')
    print('erreurs JS:', errs); assert not errs
    b.close()
# sauvegardes
info = json.load(urllib.request.urlopen(B+'/api/backup/info')); print('info sauvegarde', info)
z = urllib.request.urlopen(B+'/api/backup.zip').read(); print('zip', len(z), z[:2]); assert z[:2] == b'PK'
print('OK')
