#!/usr/bin/env python3
"""Сборка лендинга Ketology под несколько языков.

  python3 build.py build                     — собрать все локали из content/*.json
  python3 build.py build --base https://cdn.example.com/ketology/
                                             — абсолютные пути к ассетам (для екома)
  python3 build.py new en                    — завести новую локаль из ru.json
  python3 build.py check                     — проверить локали без сборки

На каждую локаль получается два файла:
  dist/<lang>/index.html     — самостоятельная страница (для превью и GitHub Pages)
  dist/<lang>/fragment.html  — <style> + <main> без шапки/подвала, это вставляется в еком
"""
import argparse, json, pathlib, re, sys

ROOT = pathlib.Path(__file__).parent
TEMPLATE = ROOT / 'src' / 'template.html'
CONTENT = ROOT / 'content'
DIST = ROOT / 'dist'
PLACEHOLDER = re.compile(r'\{\{([\w.]+)\}\}')
TODO = 'TODO: '


def load(lang):
    return json.loads((CONTENT / f'{lang}.json').read_text(encoding='utf-8'))


def locales():
    return sorted(p.stem for p in CONTENT.glob('*.json'))


def render(tpl, data, lang):
    missing = []

    def sub(m):
        key = m.group(1)
        if key == 'meta.lang':
            return lang
        if key not in data:
            missing.append(key)
            return m.group(0)
        return data[key]

    return PLACEHOLDER.sub(sub, tpl), missing


def to_fragment(page, lang):
    """Вырезает то, что реально вставляется в еком: стили + <main>.

    WHY: шапка и подвал приходят от ru.siberianhealth.com, из фрагмента их надо убрать.
    Стили оставляем инлайном — у лендинга свои токены, глобальную тему екома они не трогают,
    потому что все селекторы живут внутри .ketology-lp.
    """
    style = re.search(r'<style>(.*?)</style>', page, re.S).group(1)
    main = re.search(r'<main>(.*?)</main>', page, re.S).group(1)
    fonts = re.findall(r'<link rel="preload"[^>]*>', page)
    return (
        f'<!-- Ketology LP — {lang}. Сгенерировано build.py, править content/{lang}.json -->\n'
        + '\n'.join(fonts) + '\n'
        + f'<style>\n{RESET}\n{scope_css(style)}\n</style>\n'
        + f'<div class="ketology-lp">{main}</div>\n'
    )


# WHY: изоляция нужна в ОБЕ стороны. Префикс .ketology-lp не даёт стилям лендинга
# протечь в еком, но не защищает от обратного: правила екома вида `h1{font-family:Georgia}`
# и `img{border:4px}` бьют наследование и садятся на лендинг. Сброс идёт ПЕРВЫМ,
# поэтому собственные правила лендинга (специфичнее и ниже по файлу) его перекрывают.
RESET = """/* защита от стилей страницы-хоста */
.ketology-lp,.ketology-lp *,.ketology-lp *::before,.ketology-lp *::after{
  margin:0;padding:0;border:0;outline:0;box-sizing:border-box;
  font:inherit;color:inherit;text-align:inherit;text-transform:none;
  letter-spacing:inherit;text-decoration:none;list-style:none;
  background:none;box-shadow:none;float:none;
}"""


SCOPE = '.ketology-lp'


def scope_selector(sel):
    """Один селектор → тот же селектор внутри контейнера лендинга."""
    sel = sel.strip()
    if not sel or sel.startswith('@') or sel.startswith(SCOPE):
        return sel
    if sel in (':root', 'body'):
        return SCOPE
    if sel == 'html':
        return None                      # глобальное правило странице екома не нужно
    if sel.startswith('*'):
        return SCOPE + ' ' + sel         # *, *::before → .ketology-lp *, …
    return f'{SCOPE} {sel}'


def scope_css(css):
    """Префиксует ВСЕ селекторы контейнером, чтобы стили лендинга не текли в еком.

    WHY: фрагмент вставляется в живую страницу ru.siberianhealth.com. Без этого
    `*{box-sizing}`, `img{display:block}` и `h1,h2,h3,p{margin:0}` переписали бы
    вёрстку всего сайта, а не только лендинга.
    """
    out, i, n = [], 0, len(css)
    while i < n:
        brace = css.find('{', i)
        if brace == -1:
            out.append(css[i:])
            break
        prelude = css[i:brace]
        # тело правила с учётом вложенности (@media)
        depth, j = 1, brace + 1
        while j < n and depth:
            if css[j] == '{': depth += 1
            elif css[j] == '}': depth -= 1
            j += 1
        body = css[brace + 1:j - 1]

        # WHY: комментарий перед правилом лежит в том же prelude. Если его не вынести,
        # он попадёт внутрь селектора (и запятая в нём разорвёт селектор на части).
        comments = re.findall(r'/\*.*?\*/', prelude, re.S)
        prelude = re.sub(r'/\*.*?\*/', '', prelude, flags=re.S)
        out.extend(c + '\n' for c in comments)

        head_txt = prelude.strip()
        if head_txt.startswith('@media') or head_txt.startswith('@supports'):
            out.append(f'{prelude}{{{scope_css(body)}}}')
        elif head_txt.startswith('@'):
            out.append(f'{prelude}{{{body}}}')          # @font-face и подобное — как есть
        else:
            sels = [scope_selector(s) for s in head_txt.split(',')]
            sels = [s for s in sels if s]
            if sels:
                lead = prelude[:len(prelude) - len(prelude.lstrip())]
                out.append(f'{lead}{",".join(sels)}{{{body}}}')
        i = j
    return ''.join(out)


def rebase(html, base):
    """Относительные пути к ассетам → абсолютные.

    WHY: в екоме фрагмент лежит по чужому URL, относительный `assets/…` там не разрешится.
    Переписывать надо и HTML-атрибуты, и CSS url() — иначе @font-face молча теряет шрифт.
    """
    if not base:
        return html
    base = base.rstrip('/') + '/'
    html = re.sub(r'(src|href)="assets/', lambda m: f'{m.group(1)}="{base}assets/', html)
    html = re.sub(r'url\((["\']?)assets/', lambda m: f'url({m.group(1)}{base}assets/', html)
    return html


def cmd_build(args):
    tpl = TEMPLATE.read_text(encoding='utf-8')
    ref = load('ru')
    ok = True
    for lang in locales():
        data = load(lang)
        page, missing = render(tpl, data, lang)
        extra = sorted(set(data) - set(ref))
        todo = sorted(k for k, v in data.items() if isinstance(v, str) and v.startswith(TODO))
        out = DIST / lang
        out.mkdir(parents=True, exist_ok=True)
        # WHY: dist/<lang>/ лежит на два уровня глубже assets/ — без базы пути не разрешатся
        base = args.base or '../../'
        (out / 'index.html').write_text(rebase(page, base), encoding='utf-8')
        (out / 'fragment.html').write_text(rebase(to_fragment(page, lang), base), encoding='utf-8')
        # WHY: index.html в корне — то, что отдаёт GitHub Pages. Держим его СГЕНЕРИРОВАННЫМ
        # из шаблона, иначе он разъедется с content/ru.json при первой же правке текста.
        if lang == 'ru' and not args.base:
            (ROOT / 'index.html').write_text(page, encoding='utf-8')
        status = 'ok'
        if missing:
            status = f'НЕТ КЛЮЧЕЙ: {len(missing)} ({", ".join(missing[:3])}…)'
            ok = False
        elif todo:
            status = f'непереведено: {len(todo)}'
        print(f'  {lang}: {status}{"; лишние ключи: " + ", ".join(extra) if extra else ""}')
    return 0 if ok else 1


def cmd_new(args):
    ru = load('ru')
    dst = CONTENT / f'{args.lang}.json'
    if dst.exists():
        print(f'{dst} уже есть — не трогаю')
        return 1
    # WHY: значения остаются русскими с префиксом TODO — переводчик видит исходник
    # рядом с полем, а build отдельно считает, сколько строк ещё не переведено.
    new = {k: (v if k == 'meta.lang' else TODO + v) for k, v in ru.items()}
    new['meta.lang'] = args.lang
    dst.write_text(json.dumps(new, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'{dst}: {len(new)} строк, все помечены "{TODO}"')
    return 0


def cmd_check(args):
    ref = load('ru')
    ok = True
    for lang in locales():
        data = load(lang)
        miss = sorted(set(ref) - set(data))
        extra = sorted(set(data) - set(ref))
        todo = [k for k, v in data.items() if isinstance(v, str) and v.startswith(TODO)]
        if miss or extra:
            ok = False
        print(f'  {lang}: строк {len(data)}/{len(ref)}'
              f'{", нет: " + ", ".join(miss[:5]) if miss else ""}'
              f'{", лишние: " + ", ".join(extra[:5]) if extra else ""}'
              f'{", TODO: " + str(len(todo)) if todo else ""}')
    return 0 if ok else 1


p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
sub = p.add_subparsers(dest='cmd', required=True)
b = sub.add_parser('build'); b.add_argument('--base', default=''); b.set_defaults(fn=cmd_build)
n = sub.add_parser('new'); n.add_argument('lang'); n.set_defaults(fn=cmd_new)
c = sub.add_parser('check'); c.set_defaults(fn=cmd_check)
a = p.parse_args()
sys.exit(a.fn(a))
