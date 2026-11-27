import sys; sys.path.insert(0,'tests')
from pdmh import *
import pymupdf, urllib.request
try: urllib.request.urlopen(urllib.request.Request(B+'/api/docs/Multi.pdf/project', method='DELETE'))
except Exception: pass
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={'width':1200,'height':900},accept_downloads=True); errs=[]; pg.on('pageerror',lambda e:errs.append(str(e)))
    open_doc(pg,'Multi.pdf'); pg.click('#thumbsBtn') if pg.evaluate("$('thumbs').hidden") else None; pg.wait_for_timeout(600)
    assert pg.evaluate("document.getElementById('thumbSel').hidden")
    t=pg.locator('.thumb'); print('miniatures',t.count())
    t.nth(0).click(modifiers=['Control']); t.nth(2).click(modifiers=['Control']); pg.wait_for_timeout(200)
    print(pg.inner_text('#dlSelBtn'), pg.evaluate("[...selPages]"))
    with pg.expect_download() as d: pg.click('#dlSelBtn')
    f=d.value; path='/tmp/extrait.pdf'; f.save_as(path); print(f.suggested_filename)
    doc=pymupdf.open(path); txt=[pg_.get_text()[:8] for pg_ in doc]; print(doc.page_count, txt)
    assert doc.page_count==2 and txt[0].startswith('Page 1') and txt[1].startswith('Page 3')
    # plage avec Maj
    pg.click('.thumbclr'); t.nth(0).click(modifiers=['Control']); t.nth(2).click(modifiers=['Shift']); print([*pg.evaluate("[...selPages]")]); assert pg.evaluate("selPages.size")==3
    # téléchargement complet toujours entier
    with pg.expect_download() as d2: pg.click('#download')
    d2.value.save_as('/tmp/full.pdf'); assert pymupdf.open('/tmp/full.pdf').page_count==3
    # un simple clic navigue toujours
    pg.click('.thumbclr'); t.nth(1).click(); pg.wait_for_timeout(500); print('page courante',pg.evaluate("document.querySelector('.thumb.current')?.dataset.n"))
    print('erreurs',errs); assert not errs; print("OK")
