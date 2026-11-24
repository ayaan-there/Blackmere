"""One-time build: inline CSS (with fonts) and JS into index.html.
Source files styles.css / app.js / fonts.css remain for editing; rerun this
after changing them. api_server serves the single inlined index.html.
"""
import pathlib, base64, re

HERE = pathlib.Path(__file__).resolve().parent
html = (HERE / 'index.html').read_text(encoding='utf-8')
# make idempotent: restore placeholders from a previously inlined build
html = re.sub(r'<style>.*?</style>', '<link rel="stylesheet" href="styles.css">',
              html, count=1, flags=re.S)
html = re.sub(r'<script>.*?</script>', '<script src="app.js"></script>',
              html, count=1, flags=re.S)
css = (HERE / 'styles.css').read_text(encoding='utf-8')
fonts = (HERE / 'fonts.css').read_text(encoding='utf-8')
js = (HERE / 'app.js').read_text(encoding='utf-8')

# inline each woff2 as a data URI -> zero font requests over ngrok
def embed(m):
    name = m.group(1)
    data = base64.b64encode((HERE / 'fonts' / name).read_bytes()).decode()
    return f"url(data:font/woff2;base64,{data}) format('woff2')"

fonts = re.sub(r"url\(fonts/([\w.-]+\.woff2)\) format\('woff2'\)", embed, fonts)
css = css.replace("@import url('fonts.css');   /* self-hosted: no external network round-trip */", fonts)

html = html.replace('<link rel="stylesheet" href="styles.css">', '<style>\n' + css + '\n</style>')
html = html.replace('<script src="app.js"></script>', '<script>\n' + js + '\n</script>')

(HERE / 'index.html').write_text(html, encoding='utf-8')
print('inlined index.html:', len(html), 'bytes')
