from playwright.sync_api import sync_playwright
B='http://127.0.0.1:5055'
def fresh():
    import urllib.request
    urllib.request.urlopen(urllib.request.Request(B+'/api/docs/Test.pdf/project', method='DELETE'))

def open_doc(pg, name='Test.pdf'):
    pg.goto(B+'/#/'+name); pg.wait_for_selector('.page', timeout=15000); pg.wait_for_timeout(800)
