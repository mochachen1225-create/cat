#!/usr/bin/env python3
"""Build the English and Japanese pages from index.html (the Chinese source).

  python3 tools/build-i18n.py extract   # list every Chinese string -> i18n/catalog.json
  python3 tools/build-i18n.py build     # write en.html and ja.html using i18n/en.json, i18n/ja.json

Translation files map the exact Chinese source text to its translation. Strings on a line
containing "i18n-skip" are left alone. Anything without a translation stays Chinese and is reported.
"""
import json, re, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / 'index.html'
CJK = re.compile(r'[぀-ヿ㐀-鿿＀-￯]')
REGEX_PREV = set('(,=:[!&|?{};+-*%<>~^')

def js_units(js, base):
    """Top-level string/template literals in a JS source, as (start, end, quote, body)."""
    units, i, n = [], 0, len(js)
    last = ''   # last significant char, to tell regex literals from division

    def skip_string(i, q):
        i += 1
        while js[i] != q:
            i += 2 if js[i] == '\\' else 1
        return i + 1

    def skip_regex(i):
        i += 1; cls = False
        while True:
            c = js[i]
            if c == '\\': i += 2; continue
            if c == '[': cls = True
            elif c == ']': cls = False
            elif c == '/' and not cls: break
            i += 1
        i += 1
        while i < n and js[i].isalpha(): i += 1
        return i

    def skip_code(i, stop):
        """Skip code until the matching `stop` brace; handles nested strings/templates/regex."""
        depth, prev = 0, '{'
        while True:
            c = js[i]
            if c in '\'"': i = skip_string(i, c); prev = 'a'; continue
            if c == '`': i = skip_template(i); prev = 'a'; continue
            if c == '/' and js[i+1] == '/': i = js.index('\n', i); continue
            if c == '/' and js[i+1] == '*': i = js.index('*/', i) + 2; continue
            if c == '/' and prev in REGEX_PREV: i = skip_regex(i); prev = 'a'; continue
            if c == '{': depth += 1
            elif c == '}':
                if depth == 0: return i + 1
                depth -= 1
            if not c.isspace(): prev = c
            i += 1

    def skip_template(i):
        i += 1
        while js[i] != '`':
            if js[i] == '\\': i += 2; continue
            if js.startswith('${', i): i = skip_code(i + 2, '}'); continue
            i += 1
        return i + 1

    while i < n:
        c = js[i]
        if c == '/' and js[i+1:i+2] == '/': i = js.index('\n', i); continue
        if c == '/' and js[i+1:i+2] == '*': i = js.index('*/', i) + 2; continue
        if c in '\'"`':
            j = skip_template(i) if c == '`' else skip_string(i, c)
            units.append((base + i, base + j, c, js[i+1:j-1]))
            i = j; last = 'a'; continue
        if c == '/' and (last in REGEX_PREV or last == ''):
            i = skip_regex(i); last = 'a'; continue
        if not c.isspace():
            # keywords that can precede a regex
            last = c if not js[max(0,i-6):i+1].endswith('return') else '('
        i += 1
    return units

def all_units(src):
    out = []
    head_end = src.index('<style>')
    # head text and attributes (title, meta descriptions)
    for m in re.finditer(r'>([^<>]+)<|content="([^"]+)"', src[:head_end]):
        g = 1 if m.group(1) is not None else 2
        out.append((m.start(g), m.end(g), '', m.group(g)))
    a = src.index('<script>') + len('<script>'); b = src.rindex('</script>')
    out += [(s+1, e-1, q, body) for s, e, q, body in js_units(src[a:b], a)]
    keep = []
    for s, e, q, body in out:
        if not CJK.search(body): continue
        line = src[src.rfind('\n', 0, s)+1 : src.find('\n', e)]
        if 'i18n-skip' in line: continue
        keep.append((s, e, q, body, line.strip()))
    return keep

def escape(t, q):
    # translations use typographic quotes (’ “ ”), so only plain string literals need a safety net;
    # template literals carry code inside ${...} and are inserted exactly as written
    if q == "'": return re.sub(r"(?<!\\)'", r"\\'", t)
    if q == '"': return re.sub(r'(?<!\\)"', r'\\"', t)
    if q == '`': return t
    return t.replace('"', '&quot;')

def main():
    src = SRC.read_text()
    units = all_units(src)
    if sys.argv[1:] == ['extract']:
        seen, cat = set(), []
        for s, e, q, body, line in units:
            if body in seen: continue
            seen.add(body); cat.append({'zh': body, 'context': line[:300]})
        (ROOT / 'i18n/catalog.json').write_text(json.dumps(cat, ensure_ascii=False, indent=1))
        print(f'{len(cat)} strings -> i18n/catalog.json')
        return
    for lang, html_lang, page in (('en', 'en', 'en.html'), ('ja', 'ja', 'ja.html')):
        tr = json.loads((ROOT / f'i18n/{lang}.json').read_text())
        out, missing = src, []
        for s, e, q, body, line in sorted(units, key=lambda u: -u[0]):
            t = tr.get(body)
            if t is None: missing.append(body); continue
            out = out[:s] + escape(t, q) + out[e:]
        out = out.replace('<html lang="zh-Hant">', f'<html lang="{html_lang}">', 1)
        out = out.replace("const LANG = 'zh';", f"const LANG = '{lang}';", 1)
        (ROOT / page).write_text(out)
        print(f'{page}: {len(units) - len(missing)} replaced, {len(missing)} missing')
        for m in missing[:20]: print('  missing:', m[:80])

if __name__ == '__main__':
    main()
