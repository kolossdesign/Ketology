#!/usr/bin/env python3
"""Правка текстов прямо на странице + управление языками.

Отдельного «режима редактирования» нет: превью само по себе редактируемое.
Клик по тексту — фрейм подсвечивается и встаёт в правку, увод фокуса — сохранено.

Языки переключаются на клиенте: в страницу зашиты ВСЕ локали, поэтому можно
добавить новый язык и сразу набивать в него текст, ничего не пересобирая.
Наружу всё уезжает файлом locales.json → `python3 build.py import-locales`.

WHY <x-t>, а не <span>: обычный span поймали бы существующие селекторы вёрстки
(например `.stat__v span{font-size:32px}` уменьшил бы число КБЖУ).
"""
import json, re

PLACEHOLDER = re.compile(r'\{\{([\w.]+)\}\}')


def in_markup_context(html, pos):
    """True, если плейсхолдер стоит внутри тега, <title> или CSS — оборачивать нельзя."""
    before = html[:pos]
    if before.rfind('<') > before.rfind('>'):
        return True
    if before.rfind('<title>') > before.rfind('</title>'):
        return True
    if before.rfind('<style>') > before.rfind('</style>'):
        return True
    return False


def render_editable(tpl, data, lang):
    """Обычный рендер, но видимый текст обёрнут в <x-t data-k>."""
    # alt и aria-label обернуть тегом нельзя — помечаем сам элемент
    tpl = re.sub(r'(alt|aria-label)="\{\{([\w.]+)\}\}"',
                 lambda m: f'{m.group(1)}="{{{{{m.group(2)}}}}}" data-k-{m.group(1)}="{m.group(2)}"',
                 tpl)
    out, last = [], 0
    for m in PLACEHOLDER.finditer(tpl):
        key = m.group(1)
        value = lang if key == 'meta.lang' else data.get(key, m.group(0))
        out.append(tpl[last:m.start()])
        out.append(value if in_markup_context(tpl, m.start())
                   else f'<x-t data-k="{key}">{value}</x-t>')
        last = m.end()
    out.append(tpl[last:])
    return ''.join(out)


def hidden_keys(tpl, data):
    """Ключи, которых на странице не видно: alt, aria-label, title, description, CSS."""
    seen = []
    for m in PLACEHOLDER.finditer(tpl):
        k = m.group(1)
        if k != 'meta.lang' and in_markup_context(tpl, m.start()) and k not in seen:
            seen.append(k)
    return [k for k in data if k in seen]


CSS = '''
x-t{display:inline;font:inherit;color:inherit;letter-spacing:inherit}
x-t:focus{outline:none}
/* WHY: рамку рисуем на РОДИТЕЛЕ. Инлайновый элемент в несколько строк обводится
   по каждой строке — получается «лапша». Родитель и есть текстовый фрейм. */
.lp-frame{border-radius:4px}
.lp-frame:focus-within{outline:2px solid #EE4729;outline-offset:6px;
  background:rgba(238,71,41,.05)}

#lp-bar{position:fixed;left:0;right:0;bottom:0;z-index:100000;
  font:14px/1.4 system-ui,sans-serif;background:#161616;color:#fff}
.lp-row{display:flex;gap:10px;align-items:center;padding:9px 16px;flex-wrap:wrap}
.lp-row + .lp-row{border-top:1px solid #2e2e2e}
#lp-bar b{font-weight:600}
#lp-bar .sp{margin-left:auto}
#lp-bar button{font:inherit;padding:6px 12px;border-radius:6px;border:1px solid #555;
  background:#2a2a2a;color:#fff;cursor:pointer}
#lp-bar button:hover{background:#3a3a3a}
#lp-bar .primary{background:#EE4729;border-color:#EE4729;font-weight:600}
#lp-bar .primary:hover{background:#D23A00}
.lp-lang{display:inline-flex;align-items:center;border:1px solid #555;border-radius:6px;
  overflow:hidden}
#lp-bar .lp-lang button{border:0;border-radius:0;padding:6px 12px;background:#2a2a2a}
/* WHY: селектор с id (#lp-bar button) перебивал прежнее правило по
   специфичности, и активный язык ничем не выделялся. */
#lp-bar .lp-lang button.on{background:#EE4729;font-weight:600;color:#fff}
#lp-bar .lp-lang:has(button.on){border-color:#EE4729}
.lp-lang .del{padding:6px 8px;background:#222;color:#ff8f78;border-left:1px solid #555}
#lp-bar .lp-lang .del{padding:6px 8px;background:#222;color:#ff8f78}
.lp-lang .del:hover{background:#402020}
.lp-status{font-weight:600}
body{padding-bottom:110px}
'''

JS = r'''
(function () {
  var STORE = 'ketology-locales';
  var bar, current = CURRENT;

  var state = {locales: {}, removed: []};
  try {
    var raw = JSON.parse(localStorage.getItem(STORE) || 'null');
    if (raw && raw.locales) state = raw;
  } catch (e) {}
  function save() {
    state.dirty = true;
    localStorage.setItem(STORE, JSON.stringify(state));
    updateStatus();
  }

  function pending() {
    return !!state.dirty && !!(Object.keys(state.locales).length || state.removed.length);
  }

  var changedCount = 0;

  function updateStatus() {
    var el = bar && bar.querySelector('.lp-status');
    if (!el) return;
    // WHY: статус ровно один. Сколько блоков затронуто — уточнение в скобках,
    // а не второй индикатор рядом.
    if (pending()) {
      el.textContent = '● есть несохранённые изменения' +
        (changedCount ? ' (' + changedCount + ')' : '');
      el.style.color = '#FFD600';
    } else {
      el.textContent = '✓ изменения сохранены';
      el.style.color = '#8ede9a';
    }
  }

  // WHY: главный риск — закрыть вкладку и потерять работу. Браузер переспросит.
  window.addEventListener('beforeunload', function (e) {
    if (pending()) { e.preventDefault(); e.returnValue = ''; }
  });

  function names() {
    var out = {};
    Object.keys(LOCALES).forEach(function (c) { out[c] = LANG_NAMES[c] || c.toUpperCase(); });
    Object.keys(state.locales).forEach(function (c) {
      out[c] = state.locales[c].name || LANG_NAMES[c] || c.toUpperCase();
    });
    state.removed.forEach(function (c) { delete out[c]; });
    return out;
  }
  function dataOf(code) {
    var base = LOCALES[code] || {}, over = (state.locales[code] || {}).data || {}, out = {};
    ORDER.forEach(function (k) { out[k] = (over[k] != null ? over[k] : base[k]); });
    return out;
  }

  function clean(html) {
    return html.replace(/<br\s*\/?>/gi, '<br>').replace(/<(?!br>)[^>]*>/g, '').trim();
  }
  function frameOf(n) {
    var p = n.parentElement;
    return (p && p !== document.body) ? p : n;
  }
  function put(key, value) {
    if (!state.locales[current]) state.locales[current] = {name: names()[current], data: {}};
    state.locales[current].data[key] = value;
    save();
  }

  // WHY: у человека спрашиваем только название. Код нужен технически — он
  // становится именем файла, адресом /xx/ и атрибутом lang, — поэтому выводим
  // его сами: по словарю, иначе из первых латинских букв названия.
  var CODES = {
    'italiano': 'it', 'italian': 'it', 'итальянский': 'it',
    'espanol': 'es', 'español': 'es', 'spanish': 'es', 'испанский': 'es',
    'portugues': 'pt', 'português': 'pt', 'portuguese': 'pt', 'португальский': 'pt',
    'polski': 'pl', 'polish': 'pl', 'польский': 'pl',
    'deutsch': 'de', 'german': 'de', 'немецкий': 'de',
    'francais': 'fr', 'français': 'fr', 'french': 'fr', 'французский': 'fr',
    'english': 'en', 'английский': 'en',
    'русский': 'ru', 'russian': 'ru',
    'nederlands': 'nl', 'dutch': 'nl', 'нидерландский': 'nl',
    'čeština': 'cs', 'cestina': 'cs', 'czech': 'cs', 'чешский': 'cs',
    'română': 'ro', 'romana': 'ro', 'romanian': 'ro', 'румынский': 'ro',
    'українська': 'uk', 'ukrainian': 'uk', 'украинский': 'uk',
    'қазақша': 'kk', 'kazakh': 'kk', 'казахский': 'kk',
    'türkçe': 'tr', 'turkce': 'tr', 'turkish': 'tr', 'турецкий': 'tr',
    '中文': 'zh', 'chinese': 'zh', 'китайский': 'zh',
    'magyar': 'hu', 'hungarian': 'hu', 'венгерский': 'hu',
    'български': 'bg', 'bulgarian': 'bg', 'болгарский': 'bg',
    'srpski': 'sr', 'serbian': 'sr', 'сербский': 'sr',
    'suomi': 'fi', 'finnish': 'fi', 'финский': 'fi',
    'latviešu': 'lv', 'latvian': 'lv', 'латышский': 'lv',
    'lietuvių': 'lt', 'lithuanian': 'lt', 'литовский': 'lt',
    'eesti': 'et', 'estonian': 'et', 'эстонский': 'et'
  };

  function codeFor(title) {
    var key = title.toLowerCase().trim();
    var code = CODES[key];
    if (!code) {
      var latin = key.replace(/[^a-z]/g, '');
      code = latin.slice(0, 2) || 'l' + (Object.keys(names()).length + 1);
    }
    var taken = names(), base = code, n = 2;
    while (taken[code]) { code = base.slice(0, 1) + n; n++; }   // код занят — подбираем свободный
    return code;
  }

  function baseOf(code) {
    // WHY: у языка, добавленного в браузере, нет опубликованной версии. Считаем
    // изменения относительно того языка, с которого его скопировали, иначе
    // счётчик сразу показывает «изменено 80» на пустом месте.
    if (LOCALES[code]) return LOCALES[code];
    var src = (state.locales[code] || {}).from;
    return (src && LOCALES[src]) || {};
  }

  function markAll() {
    // WHY: изменённый блок НЕ подсвечиваем — после снятия фокуса он должен
    // выглядеть ровно так же, как на боевой странице. Счёт ведём в панели.
    var base = baseOf(current), cnt = 0;
    document.querySelectorAll('x-t[data-k]').forEach(function (n) {
      var was = String(base[n.dataset.k] == null ? '' : base[n.dataset.k]).replace(/&nbsp;/g, ' ');
      var now = clean(n.innerHTML).replace(/&nbsp;/g, ' ');
      if (now !== was) cnt++;
    });
    changedCount = cnt;
    updateStatus();
  }

  function apply(code) {
    current = code;
    var d = dataOf(code);
    document.documentElement.lang = code;
    document.querySelectorAll('x-t[data-k]').forEach(function (n) {
      if (d[n.dataset.k] != null) n.innerHTML = d[n.dataset.k];
    });
    document.querySelectorAll('[data-k-alt]').forEach(function (n) {
      if (d[n.dataset.kAlt] != null) n.setAttribute('alt', d[n.dataset.kAlt]);
    });
    document.querySelectorAll('[data-k-aria-label]').forEach(function (n) {
      if (d[n.dataset.kAriaLabel] != null) n.setAttribute('aria-label', d[n.dataset.kAriaLabel]);
    });
    if (d['meta.title']) document.title = d['meta.title'];
    var u = new URL(location.href);
    u.searchParams.set('lang', code);
    history.replaceState(null, '', u);
    renderLangs();
    markAll();
  }

  document.querySelectorAll('x-t[data-k]').forEach(function (n) {
    frameOf(n).classList.add('lp-frame');
    n.setAttribute('contenteditable', 'true');
    n.setAttribute('spellcheck', 'false');
    // WHY: из Word прилетает разметка со шрифтами и цветами — вставляем только текст
    n.addEventListener('paste', function (e) {
      e.preventDefault();
      var t = (e.clipboardData || window.clipboardData).getData('text/plain');
      document.execCommand('insertText', false, t.replace(/\s*\n\s*/g, ' ').trim());
    });
    n.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); document.execCommand('insertHTML', false, '<br>'); }
      if (e.key === 'Escape') n.blur();
    });
    // WHY: текст кнопок лежит внутри <a>. Клик по нему уходил в переход по ссылке,
    // курсор не вставал, и правка молча не сохранялась. Гасим переход и ставим курсор.
    var link = n.parentElement && n.parentElement.closest('a');
    if (link) {
      link.setAttribute('draggable', 'false');
      link.addEventListener('click', function (e) { e.preventDefault(); });
      n.addEventListener('mousedown', function () { setTimeout(function () { n.focus(); }, 0); });
    }
    n.addEventListener('blur', function () {          // сохраняем по снятию фокуса
      put(n.dataset.k, clean(n.innerHTML));
      markAll();
    });
  });

  function renderLangs() {
    var nm = names(), codes = Object.keys(nm);
    var dl = '<span class="sp"></span>' +
      '<button data-act="one">Скачать язык</button>' +
      '<button data-act="all">Скачать все</button>';
    bar.querySelector('.lp-langs').innerHTML = '<b>Язык:</b>' + codes.map(function (c) {
      return '<span class="lp-lang"><button data-lang="' + c + '" class="' +
        (c === current ? 'on' : '') + '">' + nm[c] + '</button>' +
        (codes.length > 1 ? '<button class="del" data-del="' + c + '" title="Удалить язык">×</button>' : '') +
        '</span>';
    }).join('') + '<button data-act="add">+ Добавить язык</button>' + dl;
  }

  function download(name, text) {
    var a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([text], {type: 'application/json'}));
    a.download = name;
    a.click();
    URL.revokeObjectURL(a.href);
  }
  function bundle() {
    var nm = names(), out = {languages: {}, removed: state.removed};
    Object.keys(nm).forEach(function (c) { out.languages[c] = {name: nm[c], texts: dataOf(c)}; });
    return JSON.stringify(out, null, 2) + '\n';
  }

  // ── сохранение в репозиторий ────────────────────────────────────────────────
  // WHY: страница статическая, сервера нет. Единственный способ сделать правку
  // настоящей — записать файлы через GitHub API. Токен вводится один раз и
  // лежит ТОЛЬКО в этом браузере: в репозиторий он не попадает никогда.
  function token() {
    var t = (localStorage.getItem('ketology-gh-token') || '').trim();
    if (t) return t;
    // WHY: раньше при пустом ответе кнопка молча ничего не делала и выглядела
    // сломанной. Теперь объясняем, что именно нужно и где это взять.
    t = (prompt(
      'Чтобы сохранить правки в проект, нужен GitHub-токен.\n\n' +
      'Как получить: github.com/settings/personal-access-tokens/new\n' +
      '  · Repository access: Only select repositories → ' + REPOS[0].repo + '\n' +
      '  · Permissions → Contents: Read and write\n\n' +
      'Токен останется только в этом браузере. Вставьте его сюда:') || '').trim();
    if (!t) {
      say('Токен не введён — правки остались только в браузере.', true);
      return null;
    }
    localStorage.setItem('ketology-gh-token', t);
    return t;
  }

  function say(text, bad) {
    var el = bar.querySelector('.lp-status');
    el.textContent = (bad ? '⚠ ' : '') + text;
    el.style.color = bad ? '#ff8f78' : '#8ede9a';
    clearTimeout(say._t);
    say._t = setTimeout(updateStatus, 6000);
  }

  function gh(tok, method, repo, path, body) {
    var url = 'https://api.github.com/repos/' + repo + '/contents/' + path;
    var opt = {method: method, headers: {Authorization: 'token ' + tok,
               Accept: 'application/vnd.github+json'}};
    if (body) { opt.body = JSON.stringify(body); }
    return fetch(url, opt);
  }

  function shaOf(tok, repo, path) {
    return gh(tok, 'GET', repo, path + '?ref=HEAD')
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { return j && j.sha; })
      .catch(function () { return null; });
  }

  function b64(str) {
    return btoa(new Uint8Array(new TextEncoder().encode(str))
      .reduce(function (a, c) { return a + String.fromCharCode(c); }, ''));
  }

  function writeFile(tok, repo, path, text, msg) {
    return shaOf(tok, repo, path).then(function (sha) {
      var body = {message: msg, content: b64(text)};
      if (sha) body.sha = sha;
      return gh(tok, 'PUT', repo, path, body).then(function (r) {
        if (!r.ok) return r.text().then(function (t) { throw new Error(path + ': ' + t.slice(0, 120)); });
      });
    });
  }

  function deleteFile(tok, repo, path, msg) {
    return shaOf(tok, repo, path).then(function (sha) {
      if (!sha) return;
      return gh(tok, 'DELETE', repo, path, {message: msg, sha: sha});
    });
  }

  function publish(btn) {
    var tok = token();
    if (!tok) return;
    var nm = names(), codes = Object.keys(nm);
    var label = btn.textContent;
    btn.textContent = 'Сохраняю…';
    btn.disabled = true;

    var jobs = [];
    REPOS.forEach(function (r) {
      codes.forEach(function (c) {
        jobs.push([r.repo, r.dir + c + '.json',
                   JSON.stringify(dataOf(c), null, 2) + '\n']);
      });
      jobs.push([r.repo, r.dir + 'languages.json',
                 JSON.stringify({languages: nm}, null, 2) + '\n']);
    });

    // WHY: сначала одна дешёвая проверка доступа. Иначе половина файлов
    // записалась бы, а на середине вылезла ошибка прав.
    var chain = fetch('https://api.github.com/repos/' + REPOS[0].repo, {
      headers: {Authorization: 'token ' + tok, Accept: 'application/vnd.github+json'}
    }).then(function (r) {
      if (r.status === 401) throw new Error('Bad credentials');
      if (r.status === 404) throw new Error('Not Found');
      return r.json();
    }).then(function (repo) {
      if (!repo.permissions || !repo.permissions.push) throw new Error('not accessible: нет права записи');
    });
    jobs.forEach(function (j) {
      chain = chain.then(function () {
        return writeFile(tok, j[0], j[1], j[2], 'ketology: правка текстов из редактора');
      });
    });
    (state.removed || []).forEach(function (c) {
      REPOS.forEach(function (r) {
        chain = chain.then(function () {
          return deleteFile(tok, r.repo, r.dir + c + '.json', 'ketology: язык ' + c + ' удалён');
        });
      });
    });

    chain.then(function () {
      state.dirty = false;
      localStorage.setItem(STORE, JSON.stringify(state));
      btn.textContent = 'Сохранено ✓';
      updateStatus();
      setTimeout(function () { btn.textContent = label; btn.disabled = false; }, 2000);
    }).catch(function (err) {
      btn.textContent = label;
      btn.disabled = false;
      var m = String(err.message || err);
      if (m.indexOf('Bad credentials') > -1 || m.indexOf('401') > -1) {
        localStorage.removeItem('ketology-gh-token');
        say('Токен не подошёл — нажмите «Сохранить» и введите новый.', true);
      } else if (m.indexOf('Not Found') > -1 || m.indexOf('404') > -1) {
        localStorage.removeItem('ketology-gh-token');
        say('Токен не видит репозиторий. В настройках токена: Repository access → ' +
            REPOS[0].repo + '.', true);
      } else if (m.indexOf('not accessible') > -1 || m.indexOf('403') > -1) {
        say('У токена нет права записи. Нужно Permissions → Contents: Read and write.', true);
      } else {
        say('Не сохранилось: ' + m.slice(0, 120), true);
      }
    });
  }

  bar = document.createElement('div');
  bar.id = 'lp-bar';
  bar.innerHTML =
    '<div class="lp-row lp-langs"></div>' +
    '<div class="lp-row">' +
      '<span class="lp-status"></span>' +
      '<button data-act="publish" class="primary">Сохранить</button>' +
      '<button data-act="reset">Сбросить правки</button>' +
      '<span class="sp"></span>' +
    '</div>';
  document.body.appendChild(bar);

  bar.addEventListener('click', function (e) {
    var t = e.target, act = t.dataset.act;
    if (t.dataset.lang) return apply(t.dataset.lang);
    if (t.dataset.del) {
      var c = t.dataset.del;
      if (!confirm('Удалить язык «' + names()[c] + '»? Его тексты пропадут из выгрузки.')) return;
      delete state.locales[c];
      if (LOCALES[c] && state.removed.indexOf(c) === -1) state.removed.push(c);
      save();
      return apply(c === current ? Object.keys(names())[0] : current);
    }
    if (act === 'add') {
      var title = (prompt('Название языка, например Italiano:') || '').trim();
      if (!title) return;
      var code = codeFor(title);
      var from = current;
      state.removed = state.removed.filter(function (x) { return x !== code; });
      state.locales[code] = {name: title, from: from, data: dataOf(from)};
      save();
      apply(code);
      return;
    }
    if (act === 'one') return download(current + '.json',
                                       JSON.stringify(dataOf(current), null, 2) + '\n');
    if (act === 'all') return download('locales.json', bundle());
    if (act === 'publish') return publish(t);
    if (act === 'reset') {
      if (!confirm('Вернуть исходные тексты и языки? Все правки в браузере пропадут.')) return;
      localStorage.removeItem(STORE);
      location.href = location.pathname;
    }
  });

  // WHY: тексты лежат рядом с сайтом в content/*.json и читаются в рантайме —
  // тогда сохранённая правка видна всем сразу, без пересборки страницы.
  function boot() {
    var want = new URLSearchParams(location.search).get('lang');
    apply(want && names()[want] ? want : (names()[CURRENT] ? CURRENT : Object.keys(names())[0]));
    updateStatus();
  }

  fetch('../content/languages.json', {cache: 'no-store'})
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (idx) {
      if (!idx) return null;
      var codes = Object.keys(idx.languages || {}).filter(function (c) {
        return c !== 'languages';
      });
      codes.forEach(function (c) { LANG_NAMES[c] = idx.languages[c]; });
      return Promise.all(codes.map(function (c) {
        return fetch('../content/' + c + '.json', {cache: 'no-store'})
          .then(function (r) { return r.ok ? r.json() : null; })
          .then(function (d) { if (d) LOCALES[c] = d; });
      })).then(function () {
        Object.keys(LOCALES).forEach(function (c) {
          if (codes.indexOf(c) === -1) delete LOCALES[c];
        });
      });
    })
    .catch(function () {})
    .then(boot);
})();
'''


def build_page(page_html, lang, data, tpl, all_locales, lang_names, repos):
    """Страница-превью, в которой правятся и тексты, и состав языков."""
    head = ('var ORDER = %s;\nvar LOCALES = %s;\nvar LANG_NAMES = %s;\n'
            'var CURRENT = %s;\nvar REPOS = %s;\n' % (
                json.dumps(list(data), ensure_ascii=False),
                json.dumps(all_locales, ensure_ascii=False),
                json.dumps(lang_names, ensure_ascii=False),
                json.dumps(lang, ensure_ascii=False),
                json.dumps(repos, ensure_ascii=False)))
    return page_html.replace(
        '</body>', f'<style>{CSS}</style><script>{head}{JS}</script>\n</body>')
