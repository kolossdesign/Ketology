#!/usr/bin/env python3
"""Снимает шапку и подвал с ru.siberianhealth.com в src/ecom-*.html.

Запускать, когда еком поменяет свою шапку. Нужен playwright:
    pip install playwright && playwright install chromium

WHY браузер, а не curl: шапка — AngularJS-шаблон. В сыром HTML вместо «RU» и города
лежат плейсхолдеры вида [} geoService.mainLanguage.localeCode {], их подставляет JS.

Ссылки в снятой шапке ОБЕЗВРЕЖИВАЮТСЯ: href убирается, клики гасятся CSS.
Это превью — после экспорта в еком шапку и подвал отдаёт сам проект.
"""
import pathlib, re, sys

SITE = 'https://ru.siberianhealth.com/ru/'
ROOT = pathlib.Path(__file__).parent
OUT = ROOT / 'src'


def absolutize(f):
    f = re.sub(r'(href|src)="(/[^/][^"]*)"',
               lambda m: f'{m.group(1)}="https://ru.siberianhealth.com{m.group(2)}"', f)
    f = re.sub(r'(href|src)="(//[^"]*)"', lambda m: f'{m.group(1)}="https:{m.group(2)}"', f)
    return f


def deactivate(f):
    """Ссылки и кнопки остаются на вид прежними, но никуда не ведут."""
    f = re.sub(r'\shref="[^"]*"', ' data-href-disabled', f)
    f = re.sub(r'\s(ng-[a-z-]+|data-ng-[a-z-]+)="[^"]*"', '', f)
    f = re.sub(r'<script\b.*?</script>', '', f, flags=re.S)
    f = re.sub(r'<a\b', '<a tabindex="-1"', f)
    return f


def main():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={'width': 1440, 'height': 900})
        pg.goto(SITE, wait_until='domcontentloaded', timeout=120_000)
        pg.wait_for_selector('nav.navbar-top', timeout=60_000)
        pg.wait_for_timeout(8000)
        got = pg.evaluate("""() => ({
            nav: (document.querySelector('nav.navbar-top')||{}).outerHTML || '',
            hdr: (document.querySelector('header.im21--header')||{}).outerHTML || '',
            ftr: (document.querySelector('footer.os-page-footer')||{}).outerHTML || '',
            css: [...document.querySelectorAll('link[rel=stylesheet]')].map(l => l.outerHTML),
        })""")
        b.close()

    if not got['nav'] or not got['hdr']:
        sys.exit('не нашёл шапку на странице — разметка екома изменилась')

    # WHY: header.im21--header уже содержит внутри полосу navbar-top —
    # приклеивать её отдельно нельзя, иначе она задвоится.
    nav = '' if 'navbar-top_theme_restyled' in got['hdr'] else got['nav']
    chrome = deactivate(absolutize(nav + got['hdr']))
    (OUT / 'ecom-header.html').write_text(
        f'<div class="lp-ecom-chrome">{chrome}</div>', encoding='utf-8')
    (OUT / 'ecom-footer.html').write_text(
        f'<div class="lp-ecom-chrome">{deactivate(absolutize(got["ftr"]))}</div>', encoding='utf-8')
    (OUT / 'ecom-css.html').write_text(
        '\n'.join(absolutize(c) for c in got['css']) + '\n', encoding='utf-8')

    print(f'шапка: {len(chrome)} байт | подвал: {len(got["ftr"])} | стилей: {len(got["css"])}')


if __name__ == '__main__':
    main()
