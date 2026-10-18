import sys
from playwright.sync_api import sync_playwright
src, out = sys.argv[1], sys.argv[2]
PRINT_CSS = """
@page{size:A4;margin:14mm 12mm 16mm}
body{background:#fff!important;font-size:10.5pt}
.wrap{max-width:none;padding:0}
nav.toc{display:none}
figure,.tbl,.kpis,.qcard,.aw-diagram,.note,tr{break-inside:avoid}
h2,h3{break-after:avoid}
h2{margin-top:28px}
thead th{position:static}
.kpis{grid-template-columns:repeat(5,1fr)}
.findings{break-inside:auto}
.two{grid-template-columns:1fr}
.tbl{overflow:visible}
table{font-size:8.6pt}
th,td{padding:4px 6px}
tbody th{white-space:normal}
"""
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    pg = b.new_page(color_scheme="light")
    pg.goto("file://" + src); pg.wait_for_load_state("networkidle")
    pg.add_style_tag(content=PRINT_CSS)
    pg.evaluate("document.querySelectorAll('details').forEach(d=>d.open=true)")
    pg.emulate_media(media="print", color_scheme="light")
    pg.pdf(path=out, format="A4", print_background=True, display_header_footer=True,
           header_template="<span></span>",
           footer_template="<div style='font-size:8px;width:100%;text-align:center;color:#888'>Industry All Weather · <span class='pageNumber'></span> / <span class='totalPages'></span></div>",
           margin={"top": "14mm", "bottom": "16mm", "left": "12mm", "right": "12mm"})
    b.close()
