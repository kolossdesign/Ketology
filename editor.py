#!/usr/bin/env python3
"""Режим редактирования: тот же лендинг, но каждый текст правится прямо на странице.

Человек открывает edit.html, кликает по блоку, вставляет текст из буфера (Ctrl+V),
нажимает «Скачать JSON» — и отдаёт файл в репозиторий. Никакого сервера не нужно:
правки живут в localStorage браузера, пока не выгружены.

WHY <x-t>, а не <span>: обычный span поймали бы существующие селекторы вёрстки
(например `.stat__v span{font-size:32px}` перекрасил бы число). Неизвестный тег
не матчится ничем, а `display:inline` ему задаём сами.
"""
import json, re

PLACEHOLDER = re.compile(r'\{\{([\w.]+)\}\}')


def in_markup_context(html, pos):
    """True, если плейсхолдер стоит внутри тега, <title> или CSS — оборачивать нельзя."""
    before = html[:pos]
    if before.rfind('<') > before.rfind('>'):
        return True                                  # внутри атрибута
    if before.rfind('<title>') > before.rfind('</title>'):
        return True
    if before.rfind('<style>') > before.rfind('</style>'):
        return True
    return False


def render_editable(tpl, data, lang):
    """Как обычный рендер, но видимый текст оборачивается в <x-t data-k>."""
    # WHY: alt и aria-label — атрибуты, обернуть их тегом нельзя. Помечаем сам элемент,
    # чтобы скрипт превью знал, какой ключ куда подставлять.
    tpl = re.sub(r'(alt|aria-label)="\{\{([\w.]+)\}\}"',
                 lambda m: f'{m.group(1)}="{{{{{m.group(2)}}}}}" data-k-{m.group(1)}="{m.group(2)}"',
                 tpl)
    out, last = [], 0
    for m in PLACEHOLDER.finditer(tpl):
        key = m.group(1)
        value = lang if key == 'meta.lang' else data.get(key, m.group(0))
        out.append(tpl[last:m.start()])
        if in_markup_context(tpl, m.start()):
            out.append(value)
        else:
            out.append(f'<x-t data-k="{key}">{value}</x-t>')
        last = m.end()
    out.append(tpl[last:])
    return ''.join(out)


def hidden_keys(tpl, data):
    """Ключи, которых на странице не видно: alt, aria-label, title, description, CSS."""
    hidden = []
    for m in PLACEHOLDER.finditer(tpl):
        k = m.group(1)
        if k != 'meta.lang' and in_markup_context(tpl, m.start()) and k not in hidden:
            hidden.append(k)
    return [k for k in data if k in hidden]


def panel(lang, data, hidden):
    rows = ''.join(
        f'<label><span>{k}</span><input data-hk="{k}" value="{_esc(data[k])}"></label>'
        for k in hidden)
    return f'''
<div id="lp-editor" data-lang="{lang}">
  <div class="lp-ed__bar">
    <b>Редактирование · {lang.upper()}</b>
    <span class="lp-ed__count">изменено: <b>0</b></span>
    <button data-act="hidden">Скрытые строки ({len(hidden)})</button>
    <button data-act="copy">Копировать JSON</button>
    <button data-act="save" class="lp-ed__primary">Скачать {lang}.json</button>
    <button data-act="reset">Сбросить</button>
  </div>
  <div class="lp-ed__hidden" hidden>
    <p>Эти строки на странице не видно — их читают поисковики и программы для незрячих.</p>
    {rows}
  </div>
</div>'''


def _esc(s):
    return (s.replace('&', '&amp;').replace('"', '&quot;')
             .replace('<', '&lt;').replace('>', '&gt;'))


CSS = '''
x-t{display:inline;font:inherit;color:inherit;letter-spacing:inherit}
x-t:hover{outline:2px dashed #EE4729;outline-offset:3px;cursor:text;border-radius:3px}
x-t:focus{outline:2px solid #EE4729;outline-offset:3px;background:rgba(238,71,41,.06)}
x-t.is-changed{background:rgba(255,214,0,.28);box-shadow:0 0 0 2px rgba(255,214,0,.28)}
#lp-editor{position:fixed;left:0;right:0;bottom:0;z-index:100000;font:14px/1.4 system-ui,sans-serif}
.lp-ed__bar{display:flex;gap:12px;align-items:center;background:#161616;color:#fff;padding:10px 16px}
.lp-ed__bar b{font-weight:600}
.lp-ed__count{margin-left:auto;opacity:.75}
#lp-editor button{font:inherit;padding:7px 14px;border-radius:6px;border:1px solid #555;
  background:#2a2a2a;color:#fff;cursor:pointer}
#lp-editor button:hover{background:#3a3a3a}
#lp-editor .lp-ed__primary{background:#EE4729;border-color:#EE4729;font-weight:600}
#lp-editor .lp-ed__primary:hover{background:#D23A00}
.lp-ed__hidden{max-height:42vh;overflow:auto;background:#1f1f1f;color:#fff;padding:14px 16px}
.lp-ed__hidden p{margin:0 0 12px;opacity:.7}
.lp-ed__hidden label{display:grid;grid-template-columns:240px 1fr;gap:10px;
  align-items:center;margin-bottom:8px}
.lp-ed__hidden span{opacity:.65;font-family:ui-monospace,monospace;font-size:12px}
.lp-ed__hidden input{font:inherit;padding:7px 10px;border-radius:6px;border:1px solid #444;
  background:#111;color:#fff}
body{padding-bottom:64px}
'''

JS = '''
(function () {
  var root = document.getElementById('lp-editor');
  var lang = root.dataset.lang;
  var STORE = 'ketology-edit-' + lang;
  var nodes = [].slice.call(document.querySelectorAll('x-t[data-k]'));
  var inputs = [].slice.call(root.querySelectorAll('[data-hk]'));
  var initial = {};
  nodes.forEach(function (n) { initial[n.dataset.k] = clean(n.innerHTML); });
  inputs.forEach(function (i) { initial[i.dataset.hk] = i.value; });

  function clean(html) {
    return html.replace(/<br\\s*\\/?>/gi, '<br>').replace(/&nbsp;/g, '\\u00a0')
               .replace(/<(?!br>)[^>]*>/g, '').trim();
  }

  var saved = {};
  try { saved = JSON.parse(localStorage.getItem(STORE) || '{}'); } catch (e) {}
  nodes.forEach(function (n) {
    if (saved[n.dataset.k] != null) n.innerHTML = saved[n.dataset.k];
  });
  inputs.forEach(function (i) {
    if (saved[i.dataset.hk] != null) i.value = saved[i.dataset.hk];
  });

  nodes.forEach(function (n) {
    n.setAttribute('contenteditable', 'true');
    n.setAttribute('spellcheck', 'false');
    // WHY: из Word прилетает разметка со шрифтами и цветами — вставляем только текст
    n.addEventListener('paste', function (e) {
      e.preventDefault();
      var t = (e.clipboardData || window.clipboardData).getData('text/plain');
      document.execCommand('insertText', false, t.replace(/\\s*\\n\\s*/g, ' ').trim());
    });
    n.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') {                 // перенос строки, а не новый абзац
        e.preventDefault();
        document.execCommand('insertHTML', false, '<br>');
      }
      if (e.key === 'Escape') n.blur();
    });
    n.addEventListener('input', mark);
    n.addEventListener('blur', mark);
  });
  inputs.forEach(function (i) { i.addEventListener('input', mark); });

  function current() {
    var out = {};
    nodes.forEach(function (n) { out[n.dataset.k] = clean(n.innerHTML); });
    inputs.forEach(function (i) { out[i.dataset.hk] = i.value; });
    return out;
  }

  function mark() {
    var cur = current(), changed = 0;
    nodes.forEach(function (n) {
      var diff = cur[n.dataset.k] !== initial[n.dataset.k];
      n.classList.toggle('is-changed', diff);
      if (diff) changed++;
    });
    inputs.forEach(function (i) {
      if (cur[i.dataset.hk] !== initial[i.dataset.hk]) changed++;
    });
    root.querySelector('.lp-ed__count b').textContent = changed;
    localStorage.setItem(STORE, JSON.stringify(cur));
  }

  function payload() {
    // порядок ключей сохраняем как в исходном файле — так диффы остаются читаемыми
    var order = ORDER, cur = current(), out = {};
    order.forEach(function (k) { out[k] = (cur[k] != null ? cur[k] : BASE[k]); });
    return JSON.stringify(out, null, 2) + '\\n';
  }

  root.addEventListener('click', function (e) {
    var act = e.target.dataset.act;
    if (!act) return;
    if (act === 'hidden') {
      var box = root.querySelector('.lp-ed__hidden');
      box.hidden = !box.hidden;
    }
    if (act === 'copy') {
      navigator.clipboard.writeText(payload()).then(function () {
        e.target.textContent = 'Скопировано ✓';
        setTimeout(function () { e.target.textContent = 'Копировать JSON'; }, 1600);
      });
    }
    if (act === 'save') {
      var a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([payload()], {type: 'application/json'}));
      a.download = lang + '.json';
      a.click();
      URL.revokeObjectURL(a.href);
    }
    if (act === 'reset') {
      if (!confirm('Вернуть исходный текст? Несохранённые правки пропадут.')) return;
      localStorage.removeItem(STORE);
      location.reload();
    }
  });

  mark();
})();
'''


# ── Обычное превью: показывает те же правки, только редактировать нельзя ──────
VIEW_CSS = '''
x-t{display:inline;font:inherit;color:inherit;letter-spacing:inherit}
#lp-draftbar{position:sticky;top:0;z-index:9998;display:flex;gap:12px;align-items:center;
  background:#FFD600;color:#161616;font:14px/1.4 system-ui,sans-serif;padding:8px 20px}
#lp-draftbar b{font-weight:600}
#lp-draftbar .sp{margin-left:auto}
#lp-draftbar button,#lp-draftbar a{font:inherit;padding:5px 12px;border-radius:6px;
  border:1px solid rgba(0,0,0,.25);background:rgba(0,0,0,.06);color:#161616;
  cursor:pointer;text-decoration:none}
#lp-draftbar button:hover,#lp-draftbar a:hover{background:rgba(0,0,0,.12)}
'''

VIEW_JS = '''
(function () {
  // WHY: правки живут в localStorage, а index.html — статический файл. Без этого
  // человек правит текст, возвращается в просмотр и видит старую версию.
  var lang = document.documentElement.lang || 'ru';
  var STORE = 'ketology-edit-' + lang;
  var saved;
  try { saved = JSON.parse(localStorage.getItem(STORE) || 'null'); } catch (e) { return; }
  if (!saved) return;

  // WHY: редактор хранит неразрывный пробел символом, а в разметке он сущностью
  // &nbsp; — без нормализации такой блок каждый раз считался бы «изменённым».
  function norm(s) { return String(s).replace(/&nbsp;/g, '\u00a0'); }

  var applied = 0;
  document.querySelectorAll('x-t[data-k]').forEach(function (n) {
    var v = saved[n.dataset.k];
    if (v == null) return;
    if (norm(v) !== norm(n.innerHTML)) applied++;
    n.innerHTML = v;
  });
  document.querySelectorAll('[alt],[aria-label]').forEach(function (n) {
    ['alt', 'aria-label'].forEach(function (a) {
      var k = n.getAttribute('data-k-' + a);
      if (k && saved[k] != null) n.setAttribute(a, saved[k]);
    });
  });
  if (saved['meta.title']) document.title = saved['meta.title'];

  var bar = document.createElement('div');
  bar.id = 'lp-draftbar';
  bar.innerHTML = '<b>Показаны ваши правки</b><span>изменено блоков: ' + applied + '</span>' +
    '<span class="sp"></span><a href="edit.html">✏ Продолжить редактирование</a>' +
    '<button data-act="dl">Скачать ' + lang + '.json</button>' +
    '<button data-act="off">Показать исходный текст</button>';
  document.body.insertBefore(bar, document.body.firstChild);

  bar.addEventListener('click', function (e) {
    var act = e.target.dataset.act;
    if (act === 'off') { location.search = '?original=1'; }
    if (act === 'dl') {
      var out = {};
      ORDER.forEach(function (k) { out[k] = (saved[k] != null ? saved[k] : BASE[k]); });
      var a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([JSON.stringify(out, null, 2) + '\\n'],
                                            {type: 'application/json'}));
      a.download = lang + '.json';
      a.click();
      URL.revokeObjectURL(a.href);
    }
  });
})();
'''


def build_view_page(page_html, lang, data):
    """Обычное превью, которое подхватывает несохранённые правки из редактора."""
    head = (f'var ORDER = {json.dumps(list(data), ensure_ascii=False)};\n'
            f'var BASE = {json.dumps(data, ensure_ascii=False)};\n')
    guard = ("if (new URLSearchParams(location.search).get('original') !== '1') {"
             + VIEW_JS + "}")
    inject = f'<style>{VIEW_CSS}</style><script>{head}{guard}</script>'
    return page_html.replace('</body>', inject + '\n</body>')


def build_edit_page(page_html, lang, data, tpl):
    hidden = hidden_keys(tpl, data)
    head = (f'var ORDER = {json.dumps(list(data), ensure_ascii=False)};\n'
            f'var BASE = {json.dumps(data, ensure_ascii=False)};\n')
    inject = (f'<style>{CSS}</style>'
              f'{panel(lang, data, hidden)}'
              f'<script>{head}{JS}</script>')
    return page_html.replace('</body>', inject + '\n</body>')
