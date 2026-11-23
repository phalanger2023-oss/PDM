"""Couleurs favorites : ajout, application, retrait, persistance d'un document à l'autre."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from pdmh import *
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={'width': 1400, 'height': 900}); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    fresh(); open_doc(pg); g = lambda e: pg.evaluate(e)
    pg.keyboard.press('d'); pg.wait_for_timeout(300)
    assert pg.locator('#drawbar .colfav-star').count() == 1
    g("(()=>{const i=document.getElementById('dStroke'); i.value='#12ab34'; i.dispatchEvent(new Event('input',{bubbles:true}))})()")
    pg.click('#drawbar .colfav-star'); print('favoris', g("localStorage.getItem('pdm_fav_colors')")); assert '#12ab34' in g("localStorage.getItem('pdm_fav_colors')")
    assert pg.locator('#drawbar .colfav-star').inner_text() == '★'
    # autre couleur, puis retrouver la favorite
    g("(()=>{const i=document.getElementById('dStroke'); i.value='#000000'; i.dispatchEvent(new Event('input',{bubbles:true}))})()")
    pg.click('#drawbar .colfav-open'); pg.click('.colfav-pop .sw'); pg.wait_for_timeout(200)
    print('couleur reprise', g("document.getElementById('dStroke').value"), g("drawDefaults.stroke")); assert g("drawDefaults.stroke") == '#12ab34'
    # nouvelle page / autre barre : la favorite est proposée aussi pour le texte
    pg.keyboard.press('t'); pg.wait_for_timeout(300)
    pg.click('#formatbar .colfav-open >> nth=0'); assert pg.locator('.colfav-pop .sw').count() == 1; pg.keyboard.press('Escape')
    # rechargement = autre session / autre document
    pg.reload(); pg.wait_for_selector('.page'); pg.wait_for_timeout(600); pg.keyboard.press('d'); pg.click('#drawbar .colfav-open'); assert pg.locator('.colfav-pop .sw').count() == 1
    pg.hover('.colfav-cell'); pg.click('.colfav-x'); assert g("localStorage.getItem('pdm_fav_colors')") == '[]'
    print('erreurs', errs); assert not errs; b.close()
