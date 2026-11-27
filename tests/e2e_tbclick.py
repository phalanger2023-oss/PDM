import sys; sys.path.insert(0,'tests')
from pdmh import *
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={'width':1300,'height':800}); errs=[]; pg.on('pageerror',lambda e:errs.append(str(e)))
    fresh(); open_doc(pg); pg.evaluate("window.scrollTo(0,0)")
    pg.keyboard.press('t'); pg.mouse.click(500,300); pg.wait_for_timeout(300); pg.keyboard.type("Bonjour le monde"); pg.wait_for_timeout(300)
    w=pg.evaluate("textboxes[0].x1-textboxes[0].x0"); print('largeur auto',round(w))
    pg.keyboard.press('Escape'); pg.wait_for_timeout(200)
    pg.evaluate("document.querySelector('input[name=mode][value=select]').click()")
    pg.mouse.click(520,310); pg.wait_for_timeout(250)
    st=pg.evaluate("[!!selected, document.activeElement.classList.contains('ed'), !!document.querySelector('.tb.editing')]"); print('simple clic [sélectionné, focus, édition]',st); assert st==[True,False,False]
    # copie / duplication de la zone entière
    pg.keyboard.press('Control+d'); pg.wait_for_timeout(300); print('zones après dupliquer',pg.evaluate("textboxes.length")); assert pg.evaluate("textboxes.length")==2
    # couleur sur toute la zone sélectionnée
    pg.evaluate("document.getElementById('fColor').value='#cc0000'; document.getElementById('fColor').dispatchEvent(new Event('input',{bubbles:true}))"); pg.wait_for_timeout(300)
    print('couleur',pg.evaluate("selected.color"))
    assert pg.evaluate("selected.color")=='#cc0000'
    # double-clic = édition + couleur sur un mot sélectionné
    box=pg.locator('.tb.selected'); bb=box.bounding_box()
    pg.mouse.dblclick(bb['x']+bb['width']*0.2,bb['y']+bb['height']/2); pg.wait_for_timeout(300)
    print('édition',pg.evaluate("!!document.querySelector('.tb.editing')")); assert pg.evaluate("!!document.querySelector('.tb.editing')")
    pg.keyboard.press('Control+a'); pg.evaluate("document.getElementById('fColor').value='#0000cc'; document.getElementById('fColor').dispatchEvent(new Event('input',{bubbles:true}))"); pg.wait_for_timeout(400)
    print('runs',pg.evaluate("JSON.stringify(selected.paras)")[:200])
    print('erreurs',errs); assert not errs; print('OK')
