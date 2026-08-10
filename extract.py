#!/usr/bin/env python3
"""src/page.ru.html → src/template.html + content/ru.json.

Разовый инструмент: вынимает из русской страницы весь видимый текст, alt и aria-label,
заменяет их на {{ключ}} и складывает значения в JSON. Запускать после правки разметки.
Тексты после этого правятся ТОЛЬКО в content/*.json.
"""
import collections, json, pathlib, re

ROOT = pathlib.Path(__file__).parent
SRC = ROOT / 'src' / 'page.ru.html'

SECT_NAMES = {'Hero': 'hero', 'МСТ + состав': 'composition', 'Баланс нутриентов': 'nutrients',
              'Сравнение': 'compare', 'Задачи': 'tasks', 'Вкусы': 'flavors',
              'Экспертный взгляд': 'expert', 'Мировое качество': 'quality',
              'Финальный CTA': 'cta'}
CYR = re.compile(r'[А-Яа-яЁё]')
TOKEN = re.compile(r'(<!--.*?-->|<[^>]+>)', re.S)

src = SRC.read_text(encoding='utf-8')
head, body = src.split('<body>', 1)
body = '<body>' + body

section, stack, cnt, content, out = 'page', [], collections.Counter(), {}, []


def key_for(role):
    cnt[(section, role)] += 1
    return f'{section}.{role}_{cnt[(section, role)]}'


def role_for(tag, attrs):
    if tag in ('h1', 'h2', 'h3'):
        return 'title'
    if tag == 'li':
        return 'li'
    if tag == 'a':
        return 'btn' if 'btn' in attrs else 'link'
    if tag == 'blockquote':
        return 'quote'
    return 'text'


for tok in TOKEN.split(body):
    if not tok:
        continue
    if tok.startswith('<!--'):
        m = re.search(r'──\s*(.+?)\s*──', tok)
        if m:
            section = SECT_NAMES.get(m.group(1), section)
        out.append(tok)
        continue
    if tok.startswith('<'):
        tag = re.match(r'</?([a-zA-Z0-9]+)', tok).group(1).lower()
        attrs, closing = tok, tok.startswith('</')
        for attr in ('alt', 'aria-label'):
            am = re.search(rf'{attr}="([^"]+)"', tok)
            if am and CYR.search(am.group(1)):
                k = key_for(attr.replace('-', ''))
                content[k] = am.group(1)
                tok = tok.replace(f'{attr}="{am.group(1)}"', f'{attr}="{{{{{k}}}}}"')
        if not closing and tag not in ('br', 'img', 'link', 'meta', 'input', 'hr'):
            stack.append((tag, attrs))
        elif closing and stack:
            stack.pop()
        out.append(tok)
        continue
    if tok.strip() and CYR.search(tok):
        tag, attrs = stack[-1] if stack else ('div', '')
        k = key_for(role_for(tag, attrs))
        content[k] = tok.strip()
        lead = tok[:len(tok) - len(tok.lstrip())]
        tail = tok[len(tok.rstrip()):]
        out.append(f'{lead}{{{{{k}}}}}{tail}')
    else:
        out.append(tok)

body_t = ''.join(out)

title = re.search(r'<title>(.*?)</title>', head, re.S).group(1).strip()
desc = re.search(r'<meta name="description" content="([^"]+)"', head).group(1)
head_t = (head.replace(f'<title>{title}</title>', '<title>{{meta.title}}</title>')
              .replace(f'content="{desc}"', 'content="{{meta.description}}"')
              .replace('<html lang="ru">', '<html lang="{{meta.lang}}">'))

# подписи колонок сравнения на мобильном живут в CSS ::after
for k, v in (('compare.mobile_ketology', ' — Кетолоджи'),
             ('compare.mobile_diet', ' — низкокалорийная диета')):
    assert f'content:"{v}"' in head_t, v
    head_t = head_t.replace(f'content:"{v}"', f'content:"{{{{{k}}}}}"')
    content[k] = v

data = {'meta.lang': 'ru', 'meta.title': title, 'meta.description': desc}
data.update(content)

(ROOT / 'src' / 'template.html').write_text(head_t + body_t, encoding='utf-8')
(ROOT / 'content' / 'ru.json').write_text(
    json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

full = head_t + body_t
ph = set(re.findall(r'\{\{([\w.]+)\}\}', full))
clean = re.sub(r'/\*.*?\*/', '', re.sub(r'<!--.*?-->', '', full, flags=re.S), flags=re.S)
leaks = [l.strip()[:80] for l in clean.splitlines() if CYR.search(l)]
print(f'ключей: {len(data)} | плейсхолдеров: {len(ph)} | совпало: {ph == set(data)}')
print('секции:', sorted({k.split(".")[0] for k in data}))
print('незахваченный текст:', leaks or 'нет')
