import urllib.request, re, pathlib

UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36'}
BASE = 'https://fonts.googleapis.com/css2?'
FAMS = [
    ('Inter:wght@300..700', 'inter-var.woff2'),
    ('JetBrains+Mono:wght@400..600', 'jetbrains-mono-var.woff2'),
]
HERE = pathlib.Path(__file__).resolve().parent
FONTS = HERE / 'fonts'
FONTS.mkdir(exist_ok=True)

out = []
for query, name in FAMS:
    css = urllib.request.urlopen(urllib.request.Request(BASE + 'family=' + query + '&display=swap', headers=UA), timeout=20).read().decode()
    block = next((b for s, b in re.findall(r'/\*\s*([\w-]+)\s*\*/\s*(@font-face\s*\{.*?\})', css, re.S) if s == 'latin'), None)
    if not block:
        print('no latin for', query)
        continue
    url = re.search(r'src:\s*url\((https://[^)]+\.woff2)\)', block).group(1)
    data = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20).read()
    (FONTS / name).write_bytes(data)
    block = block.replace(url, f'fonts/{name}')
    # variable faces already declare a weight range; keep as-is
    out.append(block)
    print(name, len(data), 'bytes')

(HERE / 'fonts.css').write_text('\n'.join(out), encoding='utf-8')
