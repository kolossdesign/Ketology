#!/usr/bin/env python3
"""Забирает переводы из .docx от переводчиков обратно в content/<lang>.json.

    python3 import_docx.py "путь/к/файлу.docx"

Формат файла: разделы «Russian / English / German / French» заголовками Heading 1,
внутри каждого — те же абзацы в том же порядке, что в выгрузке (docs/*.docx).

WHY позиционная сверка, а не поиск по тексту: перевод по определению не совпадает
с оригиналом, сопоставить можно только по месту. Поэтому русский раздел сверяется
с ru.json ДОСЛОВНО, и если он разъехался — импорт падает, а не пишет мусор.
"""
import difflib, json, pathlib, re, sys
from docx import Document

ROOT = pathlib.Path(__file__).parent
LANGS = {'Russian': 'ru', 'English': 'en', 'German': 'de', 'French': 'fr'}

# то, чего в документе нет (на странице не видно) — переводим отдельным словарём
SERVICE = {
 'en': {'meta.title': 'Ketology — vegan shake with MCT oils | Siberian Wellness',
        'meta.description': 'A complete meal replacement or a filling snack: a vegan shake with MCT oils, plant protein, dietary fibre and 13 vitamins.',
        'hero.alt_1': 'Ketology', 'hero.alt_2': 'Ketology shakes',
        'composition.alt_1': 'MCT oils in the Ketology formula',
        'nutrients.alt_1': 'Ketology jar', 'expert.alt_1': 'Elena Orlova',
        'quality.alt': 'Quality certificate', 'cta.alt_1': 'Ketology shake',
        'flavors.alt_1': 'Ketology Vanilla', 'flavors.alt_2': 'Ketology Peach',
        'flavors.alt_3': 'Ketology Chocolate',
        'yes': 'yes', 'no': 'no',
        'compare.mobile_ketology': ' — Ketology', 'compare.mobile_diet': ' — low-calorie diet'},
 'de': {'meta.title': 'Ketology — veganer Shake mit MCT-Ölen | Siberian Wellness',
        'meta.description': 'Vollwertiger Mahlzeitenersatz oder sättigender Snack: veganer Shake mit MCT-Ölen, pflanzlichem Protein, Ballaststoffen und 13 Vitaminen.',
        'hero.alt_1': 'Ketology', 'hero.alt_2': 'Ketology Shakes',
        'composition.alt_1': 'MCT-Öle in der Ketology-Rezeptur',
        'nutrients.alt_1': 'Ketology Dose', 'expert.alt_1': 'Elena Orlova',
        'quality.alt': 'Qualitätszertifikat', 'cta.alt_1': 'Ketology Shake',
        'flavors.alt_1': 'Ketology Vanille', 'flavors.alt_2': 'Ketology Pfirsich',
        'flavors.alt_3': 'Ketology Schokolade',
        'yes': 'ja', 'no': 'nein',
        'compare.mobile_ketology': ' — Ketology', 'compare.mobile_diet': ' — kalorienarme Diät'},
 'fr': {'meta.title': 'Ketology — shake vegan aux huiles TCM | Siberian Wellness',
        'meta.description': "Substitut de repas complet ou en-cas rassasiant : un shake vegan aux huiles TCM, protéines végétales, fibres alimentaires et 13 vitamines.",
        'hero.alt_1': 'Ketology', 'hero.alt_2': 'Shakes Ketology',
        'composition.alt_1': 'Huiles TCM dans la formule Ketology',
        'nutrients.alt_1': 'Pot Ketology', 'expert.alt_1': 'Elena Orlova',
        'quality.alt': 'Certificat de qualité', 'cta.alt_1': 'Shake Ketology',
        'flavors.alt_1': 'Ketology Vanille', 'flavors.alt_2': 'Ketology Pêche',
        'flavors.alt_3': 'Ketology Chocolat',
        'yes': 'oui', 'no': 'non',
        'compare.mobile_ketology': ' — Ketology', 'compare.mobile_diet': ' — régime hypocalorique'},
}


def sections(path):
    doc = Document(path)
    out, cur = {}, None
    for p in doc.paragraphs:
        t = p.text.strip()
        if not t:
            continue
        if p.style.name == 'Heading 1':
            cur = LANGS.get(t)
            if cur:
                out[cur] = []
            continue
        if cur:
            out[cur].append(t)
    return out


def plan(ru):
    """Тот же порядок строк, что в выгрузке: (что это, ключи)."""
    items = [('skip', []), ('skip', [])]                       # «Кетолоджи» + подзаголовок
    order = ['hero', 'composition', 'nutrients', 'compare', 'tasks', 'flavors',
             'expert', 'quality', 'cta']
    hidden = ('alt', 'arialabel', 'mobile')
    for sect in order:
        keys = [k for k in ru if k.startswith(sect + '.')
                and re.sub(r'_[\w]+$', '', k.split('.', 1)[1]) not in hidden]
        if sect == 'nutrients':
            items.append(('one', ['nutrients.title_1']))
            items.append(('one', ['nutrients.text_1']))
            for num, unit, label in [('nutrients.num_1', 'nutrients.text_2', 'nutrients.text_3'),
                                     ('nutrients.num_2', None, 'nutrients.text_4'),
                                     ('nutrients.num_3', 'nutrients.text_5', 'nutrients.text_6'),
                                     ('nutrients.num_4', 'nutrients.text_7', 'nutrients.text_8'),
                                     ('nutrients.num_5', 'nutrients.text_9', 'nutrients.text_10'),
                                     ('nutrients.num_6', None, 'nutrients.text_11')]:
                items.append(('nutri', [num, unit, label]))
            items.append(('one', ['nutrients.text_12']))
            continue
        if sect == 'compare':
            items += [('one', ['compare.title_1']), ('one', ['compare.text_1']),
                      ('one', ['compare.text_2']),
                      ('one', ['compare.text_3']), ('yes', []), ('no', []),
                      ('one', ['compare.text_4']), ('one', ['compare.text_5']),
                      ('one', ['compare.text_6']),
                      ('one', ['compare.text_7']), ('one', ['compare.text_8']),
                      ('one', ['compare.text_9'])]
            continue
        for k in keys:
            items.append(('one', [k]))
    return items


def split_nutri(text, has_unit):
    """«17.26 g — protein» / «133.21 kcal» → число, единица, подпись."""
    m = re.match(r'^\s*([\d]+(?:[.,]\d+)?)\s*(.*)$', text)
    num, rest = m.group(1), m.group(2).strip()
    rest = re.sub(r'^[—–-]\s*', '', rest).strip()
    if has_unit:
        parts = re.split(r'\s*[—–-]\s*', rest, maxsplit=1)
        if len(parts) == 2:
            return num, parts[0].strip(), parts[1].strip()
        bits = rest.split(None, 1)
        return num, bits[0], (bits[1] if len(bits) > 1 else '')
    return num, None, rest


def main():
    path = sys.argv[1]
    secs = sections(path)
    ru = json.loads((ROOT / 'content' / 'ru.json').read_text(encoding='utf-8'))
    items = plan(ru)

    counts = {k: len(v) for k, v in secs.items()}
    print('разделов в файле:', counts)
    if len(set(counts.values())) != 1:
        sys.exit('разделы разной длины — переводчик добавил или убрал абзац, сверь руками')

    def norm(t):
        return re.sub(r'\s+', ' ', t.replace('Кнопка: ', '').replace('&nbsp;', ' ')
                      .replace('<br>', ' ')).strip()

    def ru_text(kind, keys):
        if kind == 'skip':
            return None
        if kind == 'yes':
            return 'да'
        if kind == 'no':
            return 'нет'
        if kind == 'nutri':
            unit = f' {ru[keys[1]]}' if keys[1] else ''
            return f'{ru[keys[0]]}{unit} — {ru[keys[2]]}'
        return ru[keys[0]]

    # WHY: в присланном файле повторяющиеся строки схлопнуты (три кнопки «Купить» → одна).
    # Идём двумя указателями: если ожидаемый текст уже встречался и на текущем месте
    # документа лежит что-то другое — берём перевод из первого вхождения, слот не тратим.
    slots, seen, j = [], {}, 0
    for kind, keys in items:
        want = ru_text(kind, keys)
        if want is None:
            j += 1                      # шапка документа — просто пропускаем строку
            slots.append(None)
            continue
        close = (j < counts['ru'] and
                 difflib.SequenceMatcher(None, norm(secs['ru'][j]), norm(want)).ratio() > 0.6)
        if close:
            slots.append(j)
            seen.setdefault(norm(want), j)
            j += 1
        elif norm(want) in seen:
            slots.append(seen[norm(want)])        # повтор, переиспользуем
        else:
            print(f'НЕ СОШЛОСЬ на позиции {j}:')
            print(f'  жду:   {want[:80]}')
            print(f'  в док: {secs["ru"][j][:80] if j < counts["ru"] else "(конец)"}')
            sys.exit('русский раздел разъехался с ru.json — импорт остановлен')
    if j != counts['ru']:
        print(f'внимание: в документе осталось {counts["ru"] - j} неиспользованных строк')

    # русский в файле мог быть отредактирован копирайтером — показываем, что изменилось
    changes = []
    for i, (kind, keys) in enumerate(items):
        if slots[i] is None or kind != 'one':
            continue
        was, now = ru[keys[0]], re.sub(r'^[^\s:]+\s*:\s*', '', secs['ru'][slots[i]])
        if norm(was) != norm(now):
            changes.append((keys[0], was, now))
    if changes:
        print(f'\nРУССКИЙ ИЗМЕНЁН копирайтером — {len(changes)} строк:')
        for k, was, now in changes:
            print(f'  {k}\n    было:  {was[:100]}\n    стало: {now[:100]}')
        print()

    for lang in ('ru', 'en', 'de', 'fr'):
        if lang not in secs:
            print(f'{lang}: в файле нет — пропускаю')
            continue
        data, svc = {}, SERVICE.get(lang, {})
        for i, (kind, keys) in enumerate(items):
            if slots[i] is None:
                continue
            text = secs[lang][slots[i]]
            if kind == 'skip':
                continue
            if kind in ('yes', 'no'):
                continue
            if kind == 'nutri':
                num, unit, label = split_nutri(text, keys[1] is not None)
                data[keys[0]] = num
                if keys[1]:
                    data[keys[1]] = unit
                data[keys[2]] = label
                continue
            role = re.sub(r'_[\w]+$', '', keys[0].split('.', 1)[1])
            if role == 'btn':
                # WHY: переводчики локализовали и служебный префикс — «Bouton :», «Button:»
                text = re.sub(r'^[^\s:]+\s*:\s*', '', text)
            data[keys[0]] = text

        # служебные строки, которых в документе нет
        for k in ru:
            if k in data:
                continue
            role = re.sub(r'_[\w]+$', '', k.split('.', 1)[1])
            if role == 'arialabel' and svc:
                data[k] = svc['yes'] if ru[k] in ('да', 'есть') else svc['no']
            elif k.startswith('quality.alt') and 'quality.alt' in svc:
                data[k] = svc['quality.alt']
            elif k in svc:
                data[k] = svc[k]
            else:
                data[k] = ru[k]
        data['meta.lang'] = lang

        out = {k: data[k] for k in ru}
        (ROOT / 'content' / f'{lang}.json').write_text(
            json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f'{lang}: записано {len(out)} строк')


if __name__ == '__main__':
    main()
