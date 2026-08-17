#!/usr/bin/env python3
"""Мокап лендинга программы лояльности: page.html + шапка/подвал екома → index.html.

Отдельно от основного build.py: это черновик под обсуждение, без локалей
и редактора. Разметка живёт в page.html, здесь только подстановка хрома.
"""
import pathlib

ROOT = pathlib.Path(__file__).parent
SRC = ROOT.parent / 'src'

CHROME_CSS = ('<style>'
              '.lp-ecom-chrome a,.lp-ecom-chrome button{pointer-events:none;cursor:default}'
              '.lp-ecom-chrome .digi-search-highlight{display:none!important}'
              '.lp-ecom-chrome{overflow-x:hidden}'
              '</style>')


def part(name):
    p = SRC / f'ecom-{name}.html'
    return p.read_text(encoding='utf-8') if p.exists() else ''


html = (ROOT / 'page.html').read_text(encoding='utf-8')
html = (html.replace('<!--ECOM_CSS-->', part('css'))
            .replace('<!--ECOM_HEADER-->', CHROME_CSS + part('header'))
            .replace('<!--ECOM_FOOTER-->', part('footer')))
(ROOT / 'index.html').write_text(html, encoding='utf-8')
print('loyalty/index.html:', len(html) // 1024, 'КБ')
