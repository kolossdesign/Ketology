#!/usr/bin/env python3
"""Сборка лендинга Ketology под несколько языков.

  python3 build.py build                     — собрать все локали из content/*.json
  python3 build.py build --base https://cdn.example.com/ketology/
                                             — абсолютные пути к ассетам (для екома)
  python3 build.py new en                    — завести новую локаль из ru.json
  python3 build.py check                     — проверить локали без сборки
  python3 build.py find "кусок текста"        — найти ключ и все его переводы
  python3 build.py import-locales locales.json — забрать языки из редактора
  python3 build.py handover --base https://cdn/…/ — папка для передачи в еком

На каждую локаль получается два файла:
  dist/<lang>/index.html     — самостоятельная страница (для превью и GitHub Pages)
  dist/<lang>/fragment.html  — <style> + <main> без шапки/подвала, это вставляется в еком
"""
import argparse, json, pathlib, re, shutil, sys

import editor

ROOT = pathlib.Path(__file__).parent
TEMPLATE = ROOT / 'src' / 'template.html'
CONTENT = ROOT / 'content'
DIST = ROOT / 'dist'
PLACEHOLDER = re.compile(r'\{\{([\w.]+)\}\}')
TODO = 'TODO: '


LANG_NAMES = {'ru': 'Русский', 'en': 'English', 'de': 'Deutsch',
              'fr': 'Français', 'pl': 'Polski'}
# WHY: один репозиторий. Он же исходники, он же публикация — GitHub Actions
# пересобирает сайт сам. Токену в браузере нужен доступ ровно к нему одному.
REPOS = [{'repo': 'kolossdesign/Ketology', 'dir': 'content/'}]

_names_file = pathlib.Path(__file__).parent / 'content' / 'languages.json'
if _names_file.exists():
    LANG_NAMES.update(json.loads(_names_file.read_text(encoding='utf-8')).get('languages', {}))


def load(lang):
    return json.loads((CONTENT / f'{lang}.json').read_text(encoding='utf-8'))


def ecom(part):
    """Шапка/подвал/стили, снятые с ru.siberianhealth.com (см. fetch_ecom.py)."""
    p = ROOT / 'src' / f'ecom-{part}.html'
    return p.read_text(encoding='utf-8') if p.exists() else ''


def preview_styles():
    """Стили для мока чужой шапки. Своей полосы у превью больше нет —
    язык и всё остальное живут в панели редактора снизу."""
    return (
        '<style>'
        # WHY: шапка и подвал в превью — макет чужого сайта. Клики гасим,
        # чтобы из превью нельзя было случайно уйти на боевой еком.
        '.lp-ecom-chrome a,.lp-ecom-chrome button{pointer-events:none;cursor:default}'
        # промо-подсказка поиска скрывается его же JS; без Angular она висит развёрнутой
        '.lp-ecom-chrome .digi-search-highlight{display:none!important}'
        # снимок шапки статичен и на узком экране не перестраивается
        '.lp-ecom-chrome{overflow-x:hidden}'
        '</style>')


# WHY: languages.json — манифест названий языков, а не локаль. Лежит в той же
# папке, поэтому исключаем явно: иначе в переключателе появляется «LANGUAGES».
SERVICE_FILES = {'languages'}


def locales():
    return sorted(p.stem for p in CONTENT.glob('*.json')
                  if not p.stem.startswith('_') and p.stem not in SERVICE_FILES)


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
    # WHY: скрипт слайдера экспертов лежит в конце страницы, вне <main>, и раньше
    # во фрагмент не попадал — в екоме второй слайд оставался скрытым навсегда.
    # Редактора здесь быть не может: он добавляется отдельно, уже после этой функции.
    scripts = re.findall(r'<script>.*?</script>', page, re.S)
    return (
        f'<!-- Ketology LP — {lang}. Сгенерировано build.py, править content/{lang}.json -->\n'
        + '\n'.join(fonts) + '\n'
        + f'<style>\n{RESET}\n{scope_css(style)}\n</style>\n'
        + f'<div class="ketology-lp">{main}</div>\n'
        + '\n'.join(scripts) + '\n'
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
    # srcset — из-за <picture>: мобильный кадр иначе остался бы с относительным путём
    html = re.sub(r'(src|href|srcset)="assets/', lambda m: f'{m.group(1)}="{base}assets/', html)
    html = re.sub(r'url\((["\']?)assets/', lambda m: f'url({m.group(1)}{base}assets/', html)
    return html


def cmd_build(args):
    tpl = TEMPLATE.read_text(encoding='utf-8')
    ref = load('ru')
    langs = locales()
    all_data = {l: load(l) for l in langs}
    # WHY: чистим dist перед сборкой. Иначе файлы удалённых языков и артефакты
    # прошлых версий остаются лежать и уезжают в публикацию.
    if DIST.exists():
        shutil.rmtree(DIST)
    ok = True
    for lang in langs:
        data = load(lang)
        page, missing = render(tpl, data, lang)
        # WHY: шапка и подвал берутся с ru.siberianhealth.com и живут только в превью.
        # В еком-фрагмент они не попадают — там их даёт сам сайт.
        page_std = (page
                    .replace('<!--ECOM_CSS-->', ecom('css'))
                    .replace('<!--ECOM_HEADER-->', preview_styles() + ecom('header'))
                    .replace('<!--ECOM_FOOTER-->', ecom('footer')))
        page = re.sub(r'<!--ECOM_(CSS|HEADER|FOOTER)-->', '', page)
        extra = sorted(k for k in set(data) - set(ref) if not k.startswith('_'))
        todo = sorted(k for k, v in data.items() if isinstance(v, str) and v.startswith(TODO))
        out = DIST / lang
        out.mkdir(parents=True, exist_ok=True)
        # WHY: dist/<lang>/ лежит на два уровня глубже assets/ — без базы пути не разрешатся
        base = args.base or '../../'
        # WHY: одна страница на всё. Правка живёт прямо в превью, отдельного
        # режима нет. Во фрагмент для екома ничего из этого не попадает.
        view = editor.render_editable(tpl, data, lang)
        view = (view.replace('<!--ECOM_CSS-->', ecom('css'))
                    .replace('<!--ECOM_HEADER-->', preview_styles() + ecom('header'))
                    .replace('<!--ECOM_FOOTER-->', ecom('footer')))
        (out / 'index.html').write_text(
            rebase(editor.build_page(view, lang, data, tpl, all_data, LANG_NAMES, REPOS), base),
            encoding='utf-8')
        # то, что вставляется в еком: без шапки, подвала и редактора
        (out / 'fragment.html').write_text(rebase(to_fragment(page, lang), base), encoding='utf-8')

        status = 'ok'
        if missing:
            status = f'НЕТ КЛЮЧЕЙ: {len(missing)} ({", ".join(missing[:3])}…)'
            ok = False
        elif todo:
            status = f'непереведено: {len(todo)}'
        print(f'  {lang}: {status}{"; лишние ключи: " + ", ".join(extra) if extra else ""}')

    # WHY: тексты публикуем рядом с сайтом. Тогда страница читает их в рантайме,
    # и правка, сохранённая в репозиторий, видна всем БЕЗ пересборки вручную.
    cdir = DIST / 'content'
    cdir.mkdir(parents=True, exist_ok=True)
    for lang in langs:
        (cdir / f'{lang}.json').write_text(
            json.dumps(all_data[lang], ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    # WHY: имя без подчёркивания — GitHub Pages прогоняет сайт через Jekyll,
    # а тот молча не отдаёт файлы, начинающиеся с «_» (отдавал 404).
    (cdir / 'languages.json').write_text(
        json.dumps({'languages': {l: LANG_NAMES.get(l, l.upper()) for l in langs}},
                   ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    # WHY: страница верхнего уровня — редирект на ru. GitHub Pages статичен,
    # серверного language negotiation нет, поэтому это meta-refresh.
    (DIST / 'index.html').write_text(
        '<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">'
        '<meta http-equiv="refresh" content="0; url=ru/">'
        '<link rel="canonical" href="ru/"><title>Ketology</title></head>'
        '<body><a href="ru/">Ketology — русская версия</a></body></html>\n',
        encoding='utf-8')
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


def cmd_import_locales(args):
    """Забирает locales.json из редактора: новые языки, правки, удаления."""
    bundle = json.loads(pathlib.Path(args.file).read_text(encoding='utf-8'))
    langs = bundle.get('languages') or {}
    if not langs:
        sys.exit('в файле нет ключа languages — это не выгрузка редактора')
    ref = load('ru') if (CONTENT / 'ru.json').exists() else None

    for code, item in sorted(langs.items()):
        texts = item.get('texts') or {}
        if ref:
            miss = [k for k in ref if k not in texts]
            if miss:
                print(f'  {code}: НЕТ {len(miss)} ключей ({", ".join(miss[:3])}…) — пропускаю')
                continue
        path = CONTENT / f'{code}.json'
        was = 'обновлён' if path.exists() else 'СОЗДАН'
        path.write_text(json.dumps(texts, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f'  {code} ({item.get("name", code)}): {was}, строк {len(texts)}')

    for code in bundle.get('removed') or []:
        path = CONTENT / f'{code}.json'
        if path.exists():
            path.unlink()
            print(f'  {code}: УДАЛЁН')
    # WHY: имена новых языков нужны переключателю — иначе он покажет голый код
    names = {c: i.get('name') for c, i in langs.items() if i.get('name')}
    (CONTENT / 'languages.json').write_text(
        json.dumps({'languages': names}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('состав языков:', ', '.join(sorted(langs)))
    return 0


def cmd_find(args):
    """Ищет строку по всем локалям и показывает ключ + где именно его править."""
    needle = args.text.lower()
    langs = locales()
    data = {l: load(l) for l in langs}
    hits = [k for k, v in data['ru'].items()
            if isinstance(v, str) and needle in v.lower()]
    # ищем и по другим языкам — вдруг искали по английскому тексту
    for l in langs:
        for k, v in data[l].items():
            if isinstance(v, str) and needle in v.lower() and k not in hits and not k.startswith('_'):
                hits.append(k)
    if not hits:
        print(f'не нашёл «{args.text}» ни в одной локали')
        return 1

    for k in hits:
        print(f'\n\033[1m{k}\033[0m')
        for l in langs:
            val = data[l].get(k, '—')
            line = line_of(l, k)
            print(f'  content/{l}.json:{line:<4} {val}')
    print(f'\nнайдено ключей: {len(hits)}. Поменяй значение в каждом языке, потом: python3 build.py build')
    return 0


def line_of(lang, key):
    """Номер строки ключа в JSON-файле — чтобы прыгнуть туда редактором."""
    for i, ln in enumerate((CONTENT / f'{lang}.json').read_text(encoding='utf-8').splitlines(), 1):
        if ln.lstrip().startswith(f'"{key}"'):
            return i
    return 0


def cmd_check(args):
    ref = load('ru')
    ok = True
    for lang in locales():
        data = load(lang)
        miss = sorted(set(ref) - set(data))
        extra = sorted(k for k in set(data) - set(ref) if not k.startswith('_'))
        todo = [k for k, v in data.items() if isinstance(v, str) and v.startswith(TODO)]
        if miss or extra:
            ok = False
        print(f'  {lang}: строк {len([k for k in data if not k.startswith("_")])}/{len(ref)}'
              f'{" [черновик]" if data.get("_draft") else ""}'
              f'{", нет: " + ", ".join(miss[:5]) if miss else ""}'
              f'{", лишние: " + ", ".join(extra[:5]) if extra else ""}'
              f'{", TODO: " + str(len(todo)) if todo else ""}')
    return 0 if ok else 1



# ── Пакет для интеграции ──────────────────────────────────────────────────────
EDITOR_MARKS = ('<x-t', 'contenteditable', 'lp-bar', 'lp-edit-btn',
                'api.github.com', 'localStorage', 'ketology-locales')


def cmd_handover(args):
    """Готовит папку для передачи в еком: фрагменты всех языков + только нужные ассеты.

    WHY: руками собирать нельзя — легко отдать превью с редактором или забыть
    картинку. Здесь же стоит проверка: если в файл просочился редактор, сборка падает.
    """
    base = args.base.rstrip('/') + '/'
    cmd_build(argparse.Namespace(base=base))

    # WHY: сначала собираем и проверяем всё в памяти и только потом пишем папку.
    # Иначе упавшая проверка оставляла бы наполовину готовый пакет, который легко
    # принять за настоящий.
    frags, used = {}, set()
    for lang in locales():
        frag = (DIST / lang / 'fragment.html').read_text(encoding='utf-8')
        bad = [m for m in EDITOR_MARKS if m in frag]
        if bad:
            print(f'  ✗ {lang}: в фрагменте следы редактора: {bad}. Пакет не собран.')
            return 1
        frags[lang] = frag
        used |= set(re.findall(re.escape(base) + r'(assets/[^"\')\s]+)', frag))

    missing = [r for r in sorted(used) if not (ROOT / r).exists()]
    if missing:
        print(f'  ✗ не хватает файлов: {missing}. Пакет не собран.')
        return 1

    out = ROOT / 'handover'
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for lang, frag in frags.items():
        (out / f'ketology-{lang}.html').write_text(frag, encoding='utf-8')
    for rel in sorted(used):
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dst)

    doc = ROOT / 'ИНСТРУКЦИЯ_ПО_ИНТЕГРАЦИИ.md'
    if doc.exists():
        shutil.copy2(doc, out / 'ИНСТРУКЦИЯ.md')

    weight = sum((out / r).stat().st_size for r in used)
    print(f'  страниц: {len(frags)} ({", ".join(sorted(frags))})')
    print(f'  ассетов: {len(used)}, вес {weight / 1048576:.2f} МБ')
    print(f'  база путей: {base}')
    print(f'  готово: {out}')
    return 0


p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
sub = p.add_subparsers(dest='cmd', required=True)
b = sub.add_parser('build'); b.add_argument('--base', default=''); b.set_defaults(fn=cmd_build)
n = sub.add_parser('new'); n.add_argument('lang'); n.set_defaults(fn=cmd_new)
c = sub.add_parser('check'); c.set_defaults(fn=cmd_check)
f = sub.add_parser('find'); f.add_argument('text'); f.set_defaults(fn=cmd_find)
i = sub.add_parser('import-locales'); i.add_argument('file'); i.set_defaults(fn=cmd_import_locales)
h = sub.add_parser('handover'); h.add_argument('--base', required=True); h.set_defaults(fn=cmd_handover)
a = p.parse_args()
sys.exit(a.fn(a))
