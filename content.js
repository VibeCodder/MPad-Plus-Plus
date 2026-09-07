(() => {
  const VERSION = 'fr_v19';
  if (window[VERSION]) return;
  window[VERSION] = true;
  ['__findReplaceLoaded','fr_v2','fr_v3','fr_v4','fr_v5','fr_v6','fr_v7','fr_v8','fr_v9','fr_v10','fr_v11','fr_v12','fr_v13','fr_v14','fr_v15','fr_v16','fr_v17','fr_v18'].forEach(k => delete window[k]);

  // ── State ────────────────────────────────────────────────────────────────
  let state = {
    search: '', replace: '', caseSensitive: false,
    wholeWord: false, searchAll: false, matches: [], current: -1,
  };

  // ── Title schema parser ──────────────────────────────────────────────────
  // Recognises the pattern:  title part1 part2 @ value
  // Everything before the LAST '@' is the human-readable label.
  // Everything after  the LAST '@' is the preset/default value.
  function parseTitleSchema(el) {
    const raw = (el.getAttribute('title') || '').trim();
    const atIdx = raw.lastIndexOf('@');
    if (atIdx === -1) return { label: null, preset: null, hasSchema: false };
    return {
      hasSchema: true,
      label:  raw.slice(0, atIdx).trim()  || null,
      preset: raw.slice(atIdx + 1).trim() || null,
    };
  }

  // ── Styles ───────────────────────────────────────────────────────────────
  const STYLE_ID = '__fr_style';
  if (!document.getElementById(STYLE_ID)) {
    const s = document.createElement('style');
    s.id = STYLE_ID;
    s.textContent = `
      .__fr_hl        { background:#ffb300 !important;color:#000 !important;border-radius:2px; }
      .__fr_hl_act    { background:#ff6d00 !important;color:#fff !important;border-radius:2px;outline:2px solid #ff6d00; }
      .__fr_hl_ro     { background:#4a90d9 !important;color:#fff !important;border-radius:2px; }
      .__fr_hl_ro_act { background:#1a6abf !important;color:#fff !important;border-radius:2px;outline:2px solid #4a90d9; }
      .__fr_toast {
        position:fixed; bottom:24px; left:50%; transform:translateX(-50%);
        background:#1a4d1a; color:#a8e6a8; border:1px solid #2d8c2d;
        padding:10px 20px; border-radius:10px; font-family:'DM Sans',sans-serif;
        font-size:13px; font-weight:600; z-index:2147483647;
        box-shadow:0 4px 20px rgba(0,0,0,.5); pointer-events:none;
        animation:__fr_fadein .2s ease;
      }
      .__fr_toast.error { background:#4d1a1a; color:#e6a8a8; border-color:#8c2d2d; }
      @keyframes __fr_fadein { from{opacity:0;transform:translateX(-50%) translateY(8px)} to{opacity:1;transform:translateX(-50%) translateY(0)} }
    `;
    document.head.appendChild(s);
  }

  // ── Toast notifications ───────────────────────────────────────────────────
  function showToast(msg, isError = false) {
    document.querySelectorAll('.__fr_toast').forEach(t => t.remove());
    const t = document.createElement('div');
    t.className = '__fr_toast' + (isError ? ' error' : '');
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 2800);
  }
  window.__frShowToast = showToast;

  // ── Find & Replace helpers ────────────────────────────────────────────────
  function buildRegex(search, caseSensitive, wholeWord) {
    if (!search) return null;
    let esc = search.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    if (wholeWord) esc = `\\b${esc}\\b`;
    return new RegExp(esc, caseSensitive ? 'g' : 'gi');
  }

  function isFormField(el) {
    if (!el) return false;
    if (el.tagName === 'INPUT') {
      return ['text','search','email','url','tel','number','password',
              'date','datetime-local','month','week','time']
              .includes((el.type || 'text').toLowerCase());
    }
    return el.tagName === 'TEXTAREA';
  }

  function nearestFormField(el) {
    let cur = el;
    while (cur && cur !== document.body) {
      if (isFormField(cur)) return cur;
      cur = cur.parentElement;
    }
    return null;
  }

  function getVal(el) { return el.isContentEditable ? el.innerText : el.value; }

  function setVal(el, value) {
    // Temporarily lift locks so the setter actually sticks
    const wasDisabled = el.disabled;
    const wasReadOnly = el.readOnly;
    if (wasDisabled) { el.removeAttribute('disabled'); el.disabled = false; }
    if (wasReadOnly) { el.removeAttribute('readonly'); el.readOnly = false; }

    if (el.isContentEditable) {
      el.innerText = value;
      el.dispatchEvent(new Event('input', { bubbles: true }));
    } else if (el.tagName === 'SELECT') {
      el.value = value;
      el.dispatchEvent(new Event('input',  { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    } else {
      const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
      if (setter) setter.call(el, value); else el.value = value;
      el.dispatchEvent(new Event('input',  { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    }

    // Restore original lock state
    if (wasDisabled) { el.disabled = true; el.setAttribute('disabled', ''); }
    if (wasReadOnly) { el.readOnly = true; el.setAttribute('readonly', ''); }
  }

  const HL_CLASSES = ['__fr_hl','__fr_hl_act','__fr_hl_ro','__fr_hl_ro_act'];

  function clearHighlights() {
    document.querySelectorAll(HL_CLASSES.map(c => '.' + c).join(',')).forEach(el => {
      const parent = el.parentNode;
      if (parent) {
        parent.replaceChild(document.createTextNode(el.textContent), el);
        parent.normalize();
      }
    });
  }

  function highlightTextNode(textNode, regex, readOnly) {
    const cls = readOnly ? '__fr_hl_ro' : '__fr_hl';
    const text = textNode.textContent;
    const hits = [];
    let m;
    regex.lastIndex = 0;
    while ((m = regex.exec(text)) !== null)
      hits.push({ start: m.index, end: m.index + m[0].length });
    if (!hits.length) return [];

    const frag = document.createDocumentFragment();
    let last = 0;
    const spans = [];
    for (const { start, end } of hits) {
      if (start > last) frag.appendChild(document.createTextNode(text.slice(last, start)));
      const sp = document.createElement('span');
      sp.className = cls;
      sp.textContent = text.slice(start, end);
      frag.appendChild(sp);
      spans.push(sp);
      last = end;
    }
    if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
    textNode.parentNode.replaceChild(frag, textNode);
    return spans;
  }

  function findAll() {
    clearHighlights();
    state.matches = [];
    state.current = -1;
    const { search, caseSensitive, wholeWord, searchAll } = state;
    if (!search) return;

    // ── Pass 1: input/textarea — these have no text node children so the
    //   TreeWalker never visits them. Query them directly.
    document.querySelectorAll('input, textarea').forEach(el => {
      if (!isFormField(el)) return;
      const style = getComputedStyle(el);
      if (style.display === 'none' || style.visibility === 'hidden') return;
      const val = getVal(el);
      const re = buildRegex(search, caseSensitive, wholeWord);
      let m; re.lastIndex = 0;
      while ((m = re.exec(val)) !== null)
        state.matches.push({ type: 'input', inputEl: el, start: m.index, end: m.index + m[0].length });
    });

    // ── Pass 2: walk all other text nodes in the DOM ──────────────────────
    const WIDGET_ROLES = new Set(['textbox','searchbox','combobox','spinbutton']);

    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        const p = node.parentElement;
        if (!p) return NodeFilter.FILTER_REJECT;
        if (['SCRIPT','STYLE','NOSCRIPT','IFRAME','INPUT','TEXTAREA'].includes(p.tagName))
          return NodeFilter.FILTER_REJECT;
        if (HL_CLASSES.some(c => p.classList.contains(c))) return NodeFilter.FILTER_REJECT;
        if (!node.textContent.trim()) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
    });

    let node;
    while ((node = walker.nextNode())) {
      const p = node.parentElement;

      // Check if inside a contenteditable that is a real input widget:
      // must have a widget ARIA role on itself or direct parent.
      const ceAncestor = p.closest('[contenteditable="true"]');
      const isWidgetCE = ceAncestor && (
        WIDGET_ROLES.has(ceAncestor.getAttribute('role')) ||
        WIDGET_ROLES.has(ceAncestor.parentElement?.getAttribute('role'))
      );

      if (isWidgetCE) {
        // Real editable widget (e.g. rich text editor with role=textbox)
        const spans = highlightTextNode(node, buildRegex(search, caseSensitive, wholeWord), false);
        spans.forEach(sp => state.matches.push({ type: 'dom', span: sp, readOnly: false }));
      } else {
        // Everything else is static page text — only included when searchAll is ON
        if (!searchAll) continue;
        // Check if this text node actually matches before trying to highlight
        const re = buildRegex(search, caseSensitive, wholeWord);
        if (!re.test(node.textContent)) continue;
        const spans = highlightTextNode(node, re, true);
        spans.forEach(sp => state.matches.push({ type: 'dom', span: sp, readOnly: true }));
      }
    }

    console.debug(`[FR] findAll: inputs=${state.matches.filter(m=>m.type==='input').length} dom=${state.matches.filter(m=>m.type==='dom').length} searchAll=${searchAll} total=${state.matches.length}`);
    if (state.matches.length) { state.current = 0; activateCurrent(); }
  }

  function activateCurrent() {
    document.querySelectorAll('.__fr_hl_act').forEach(el => el.className = '__fr_hl');
    document.querySelectorAll('.__fr_hl_ro_act').forEach(el => el.className = '__fr_hl_ro');
    if (state.current < 0 || state.current >= state.matches.length) return;
    const match = state.matches[state.current];
    if (match.type === 'dom') {
      match.span.className = match.readOnly ? '__fr_hl_ro_act' : '__fr_hl_act';
      match.span.scrollIntoView({ block: 'center', behavior: 'smooth' });
    } else {
      // Scroll into view but DON'T focus/select — that steals focus from the
      // extension popup search box and causes the user's typing to overwrite it
      match.inputEl.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }
  }

  function navigate(dir) {
    if (!state.matches.length) return;
    state.current = (state.current + dir + state.matches.length) % state.matches.length;
    activateCurrent();
  }

  function replaceCurrent(andAdvance = false) {
    if (!state.matches.length || state.current < 0) return;
    const match = state.matches[state.current];
    const prevIndex = state.current;

    if (match.type === 'dom') {
      // Replace the span with plain text in-place — no findAll() needed
      const spanParent = match.span.parentNode;
      if (spanParent) {
        spanParent.replaceChild(document.createTextNode(state.replace), match.span);
        spanParent.normalize();
      }
      // Remove just this match from the array, keep all others intact
      state.matches.splice(state.current, 1);
      if (state.matches.length === 0) {
        state.current = -1;
      } else {
        // andAdvance: move to next; otherwise stay at same index (now points to next item)
        state.current = prevIndex % state.matches.length;
        if (andAdvance) state.current = (prevIndex) % state.matches.length;
        activateCurrent();
      }
    } else {
      const el = match.inputEl;
      const val = getVal(el);
      setVal(el, val.slice(0, match.start) + state.replace + val.slice(match.end));
      const delta = state.replace.length - (match.end - match.start);
      state.matches.splice(state.current, 1);
      state.matches = state.matches.map(m =>
        (m.type === 'input' && m.inputEl === el && m.start >= match.end)
          ? { ...m, start: m.start + delta, end: m.end + delta } : m
      );
      if (state.matches.length === 0) {
        state.current = -1;
      } else {
        state.current = prevIndex % state.matches.length;
        if (andAdvance) state.current = prevIndex % state.matches.length;
        activateCurrent();
      }
    }
  }

  function replaceAll() {
    // Fresh find to get all current matches highlighted
    findAll();
    if (!state.matches.length) return;

    // Replace all input/textarea fields via value API
    const inputEls = new Set(state.matches.filter(m => m.type === 'input').map(m => m.inputEl));
    inputEls.forEach(el => {
      const re = buildRegex(state.search, state.caseSensitive, state.wholeWord);
      setVal(el, getVal(el).replace(re, state.replace));
    });

    // Replace all highlighted DOM spans in one pass — don't call findAll after,
    // that would re-highlight the newly inserted replacement text
    document.querySelectorAll('.__fr_hl,.__fr_hl_act,.__fr_hl_ro,.__fr_hl_ro_act').forEach(sp => {
      const spParent = sp.parentNode;
      if (spParent) {
        spParent.replaceChild(document.createTextNode(state.replace), sp);
        spParent.normalize();
      }
    });

    // Clear state — no remaining matches
    state.matches = [];
    state.current = -1;
  }

  // ── Form Tools ────────────────────────────────────────────────────────────

  // Collect all visible, meaningful form fields with a stable index
  function collectFormFields() {
    const fields = [];
    document.querySelectorAll('input, textarea, select, [contenteditable="true"]').forEach((el, idx) => {
      // Skip hidden, submit, button, reset, file inputs
      if (el.tagName === 'INPUT') {
        const t = (el.type || 'text').toLowerCase();
        if (['hidden','submit','button','reset','file','image','checkbox','radio'].includes(t)) return;
      }
      // Skip invisible elements
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 && rect.height === 0) return;
      const style = getComputedStyle(el);
      if (style.display === 'none' || style.visibility === 'hidden') return;

      fields.push(el);
    });
    return fields;
  }

  window.__frCopyForms = function() {
    const fields = collectFormFields();
    const data = fields.map((el, i) => {
      let value = '';
      if (el.tagName === 'SELECT') {
        value = el.value;
      } else if (el.isContentEditable) {
        value = el.innerText;
      } else {
        value = el.value;
      }
      const schema = parseTitleSchema(el);
      const label = (schema.hasSchema && schema.label)
        ? schema.label
        : (el.getAttribute('aria-label')
          || el.getAttribute('placeholder')
          || el.getAttribute('name')
          || el.getAttribute('id')
          || `field_${i}`);
      return { index: i, label, value, tag: el.tagName, type: el.type || '', schemaPreset: schema.preset };
    });

    // Send to background for storage (cross-tab clipboard)
    chrome.runtime.sendMessage({ action: 'formDataCopied', data });

    // Also write a human-readable version to system clipboard
    const text = data.map(f => `[${f.label}]: ${f.value}`).join('\n');
    navigator.clipboard.writeText(text).catch(() => {});

    showToast(`📋 Copied ${data.length} field(s)`);
    return data;
  };

  window.__frPasteForms = function() {
    chrome.runtime.sendMessage({ action: 'requestFormClipboard' }, (response) => {
      const data = response?.data;
      if (!data || !data.length) {
        showToast('⚠️ No form data in clipboard', true);
        return;
      }
      const fields = collectFormFields();
      let pasted = 0;
      data.forEach(item => {
        const el = fields[item.index];
        if (!el) return;
        if (el.tagName === 'SELECT') {
          el.value = item.value;
          el.dispatchEvent(new Event('change', { bubbles: true }));
        } else if (el.isContentEditable) {
          el.innerText = item.value;
          el.dispatchEvent(new Event('input', { bubbles: true }));
        } else {
          setVal(el, item.value);
        }
        pasted++;
      });
      showToast(`📥 Pasted into ${pasted} field(s)`);
    });
  };

  window.__frClearForms = function() {
    const fields = collectFormFields();
    fields.forEach(el => {
      if (el.tagName === 'SELECT') {
        el.selectedIndex = 0;
        el.dispatchEvent(new Event('change', { bubbles: true }));
      } else if (el.isContentEditable) {
        el.innerText = '';
        el.dispatchEvent(new Event('input', { bubbles: true }));
      } else {
        setVal(el, '');
      }
    });
    showToast(`🗑️ Cleared ${fields.length} field(s)`);
  };

  // ── Unlock all inputs ─────────────────────────────────────────────────────
  window.__frUnlockInputs = function() {
    let count = 0;

    // 1. Inject a <style> that overrides common CSS-level locks globally
    const UNLOCK_STYLE_ID = '__fr_unlock_style';
    if (!document.getElementById(UNLOCK_STYLE_ID)) {
      const s = document.createElement('style');
      s.id = UNLOCK_STYLE_ID;
      s.textContent = `
        input[disabled], textarea[disabled], select[disabled],
        input[readonly], textarea[readonly],
        input.__fr_unlocked, textarea.__fr_unlocked, select.__fr_unlocked {
          pointer-events: auto !important;
          user-select: text !important;
          opacity: 1 !important;
          cursor: text !important;
          color: inherit !important;
          background: inherit !important;
        }
      `;
      document.head.appendChild(s);
    }

    document.querySelectorAll(
      'input, textarea, select, [contenteditable]'
    ).forEach(el => {
      let unlocked = false;

      // a) disabled attribute / property
      if (el.disabled || el.hasAttribute('disabled')) {
        el.removeAttribute('disabled');
        try { el.disabled = false; } catch (_) {}
        unlocked = true;
      }

      // b) readonly attribute / property
      if (el.readOnly || el.hasAttribute('readonly')) {
        el.removeAttribute('readonly');
        try { el.readOnly = false; } catch (_) {}
        unlocked = true;
      }

      // c) aria-disabled
      if (el.getAttribute('aria-disabled') === 'true') {
        el.setAttribute('aria-disabled', 'false');
        unlocked = true;
      }

      // d) contenteditable="false"
      if (el.getAttribute('contenteditable') === 'false') {
        el.setAttribute('contenteditable', 'true');
        unlocked = true;
      }

      // e) inline style pointer-events / user-select
      const cs = getComputedStyle(el);
      if (cs.pointerEvents === 'none') {
        el.style.setProperty('pointer-events', 'auto', 'important');
        unlocked = true;
      }
      if (cs.userSelect === 'none' && el.tagName !== 'SELECT') {
        el.style.setProperty('user-select', 'text', 'important');
        unlocked = true;
      }

      // f) tabindex=-1 makes inputs unfocusable; restore to 0
      if (el.getAttribute('tabindex') === '-1') {
        el.setAttribute('tabindex', '0');
        unlocked = true;
      }

      // g) mark with helper class so the override style above applies
      el.classList.add('__fr_unlocked');
      if (unlocked) count++;
    });

    // Also unlock any element that has an onclick/onmousedown that calls preventDefault
    // by overlaying pointer-events on covering elements — best-effort via z-index scan
    document.querySelectorAll('[style*="pointer-events:none"],[style*="pointer-events: none"]').forEach(el => {
      el.style.setProperty('pointer-events', 'auto', 'important');
    });

    showToast(`🔓 Odblokowano ${count} pole(i)`);
    return count;
  };

  // ── Schema window — paste Excel table (title @ value) ────────────────────
  window.__frOpenSchemaWindow = function() {
    const WIN_ID = '__fr_schema_win';
    if (document.getElementById(WIN_ID)) { document.getElementById(WIN_ID).remove(); return; }

    const win = document.createElement('div');
    win.id = WIN_ID;
    win.innerHTML = `
      <div id="__frsw_header">
        <span id="__frsw_title">✏️ Schema: wklej z Excela</span>
        <button id="__frsw_close">✕</button>
      </div>
      <div id="__frsw_body">
        <div class="__frsw_label">Wklej tutaj dane z Excela</div>
        <div class="__frsw_hint">Każdy wiersz: <code>tytuł&nbsp;@&nbsp;wartość</code></div>
        <textarea id="__frsw_paste" placeholder="np.&#10;Imię @ Jan&#10;Nazwisko @ Kowalski&#10;Email @ jan@example.com" spellcheck="false"></textarea>
        <div id="__frsw_preview"></div>
        <div id="__frsw_btnrow">
          <button id="__frsw_clear_ta">🗑 Wyczyść</button>
          <button id="__frsw_apply" class="__frsw_primary">✅ Podstaw wartości</button>
        </div>
        <div id="__frsw_result"></div>
      </div>
    `;

    const style = document.createElement('style');
    style.id = '__frsw_style';
    style.textContent = `
      #__fr_schema_win {
        position:fixed; top:70px; right:20px; z-index:2147483647;
        width:360px; background:#141414; border:1px solid #333;
        border-radius:12px; box-shadow:0 8px 40px rgba(0,0,0,.75);
        font-family:'DM Sans',system-ui,sans-serif; color:#d4d4d4; font-size:13px;
      }
      #__fr_schema_win * { box-sizing:border-box; }
      #__frsw_header {
        display:flex; align-items:center; padding:11px 14px 10px;
        border-bottom:1px solid #2a2a2a; cursor:move;
      }
      #__frsw_title { font-weight:700; font-size:13px; flex:1; }
      #__frsw_close {
        background:none; border:none; color:#666; font-size:16px;
        cursor:pointer; padding:0 4px; line-height:1;
      }
      #__frsw_close:hover { color:#fff; }
      #__frsw_body { padding:12px 14px 14px; }
      .__frsw_label { font-size:10px; font-weight:600; color:#aaa; text-transform:uppercase; letter-spacing:.06em; margin-bottom:4px; }
      .__frsw_hint { font-size:11px; color:#666; margin-bottom:8px; }
      .__frsw_hint code { background:#252525; border:1px solid #333; border-radius:4px; padding:1px 5px; font-family:monospace; color:#9ecf9e; font-size:11px; }
      #__frsw_paste {
        width:100%; height:130px; background:#252525; border:1px solid #333;
        border-radius:8px; padding:9px 11px; font-family:monospace; font-size:12px;
        color:#d4d4d4; outline:none; resize:vertical; line-height:1.6;
      }
      #__frsw_paste:focus { border-color:#2d6a2d; box-shadow:0 0 0 2px rgba(45,106,45,.25); }
      #__frsw_preview {
        margin-top:8px; max-height:110px; overflow-y:auto;
        background:#1a1a1a; border:1px solid #2a2a2a; border-radius:8px;
        font-size:11px; font-family:monospace;
      }
      #__frsw_preview:empty { display:none; }
      .__frsw_row {
        display:flex; align-items:center; gap:6px;
        padding:5px 9px; border-bottom:1px solid #222;
      }
      .__frsw_row:last-child { border-bottom:none; }
      .__frsw_row_title { color:#aaa; flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
      .__frsw_row_arrow { color:#555; }
      .__frsw_row_value { color:#7ecf7e; flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
      .__frsw_row_match { background:#1a2e1a; }
      .__frsw_row_nomatch { opacity:.45; }
      .__frsw_row_badge {
        font-size:9px; padding:1px 5px; border-radius:4px; font-weight:700;
        background:#206020; color:#a8e6a8; white-space:nowrap; flex-shrink:0;
      }
      .__frsw_row_badge.miss { background:#3a1a1a; color:#e08080; }
      #__frsw_btnrow { display:grid; grid-template-columns:1fr 2fr; gap:7px; margin-top:10px; }
      #__frsw_btnrow button {
        padding:9px 8px; border:none; border-radius:8px; font-size:12px;
        font-weight:600; cursor:pointer; background:#1a4d1a; color:#7ecf7e;
        transition:background .15s;
      }
      #__frsw_btnrow button.__frsw_primary { background:#206020; color:#a8e6a8; }
      #__frsw_btnrow button.__frsw_primary:hover { background:#2d8c2d; }
      #__frsw_btnrow button:not(.__frsw_primary):hover { background:#206020; }
      #__frsw_result {
        margin-top:8px; font-size:11px; color:#3aaa3a; font-family:monospace;
        min-height:14px; text-align:center;
      }
      #__frsw_result.err { color:#c0392b; }
    `;
    document.head.appendChild(style);
    document.body.appendChild(win);

    // ── Drag ──────────────────────────────────────────────────────────────
    const hdr = win.querySelector('#__frsw_header');
    let dOX, dOY, dragging = false;
    hdr.addEventListener('mousedown', e => {
      if (e.target.id === '__frsw_close') return;
      dragging = true;
      dOX = e.clientX - win.getBoundingClientRect().left;
      dOY = e.clientY - win.getBoundingClientRect().top;
      e.preventDefault();
    });
    document.addEventListener('mousemove', e => {
      if (!dragging) return;
      win.style.left  = (e.clientX - dOX) + 'px';
      win.style.top   = (e.clientY - dOY) + 'px';
      win.style.right = 'auto';
    });
    document.addEventListener('mouseup', () => { dragging = false; });

    win.querySelector('#__frsw_close').addEventListener('click', () => {
      win.remove();
      document.getElementById('__frsw_style')?.remove();
    });

    // Normalize text for MATCHING purposes only (never used for the value
    // that actually gets written into the input): collapses non-breaking
    // spaces / repeated whitespace that Excel often pastes in, trims, and
    // lowercases so "Velocidad  de\u00A0centrifugado" still matches
    // "velocidad de centrifugado".
    function normText(s) {
      return (s || '')
        .replace(/\u00A0/g, ' ')
        .replace(/\s+/g, ' ')
        .trim()
        .toLowerCase();
    }

    // ── Parse pasted text ─────────────────────────────────────────────────
    // Each line: "some title text @ some value"   (last @ is the separator).
    // Only "@" is ever treated as a separator — no tab/column splitting.
    function parseLines(text) {
      return text.split(/\r\n|\r|\n/)
        .filter(line => line.trim())
        .map(line => {
          // Only @ as separator — last @ splits title from value
          const atIdx = line.lastIndexOf('@');
          if (atIdx === -1) return null;
          const title = line.slice(0, atIdx).trim();
          const value = line.slice(atIdx + 1).trim();
          if (!title) return null;
          return { title, value };
        })
        .filter(Boolean);
    }

    // True if the input has a non-empty <span> that PRECEDES it, where the
    // <span> and the input share the same <td> as their parent (per spec:
    // "tam gdzie jest ten span i input ich rodzicem jest td").
    // Spans that appear AFTER the input (e.g. error/helper text) are ignored.
    function hasPrecedingSpan(el) {
      const td = el.closest('td');
      if (td) {
        // Only look at DIRECT children of the td, in document order, and
        // stop the moment we reach the child that IS (or contains) the input —
        // everything from that point on is the input itself or comes after it.
        const children = Array.from(td.children);
        for (const child of children) {
          if (child === el || child.contains(el)) break;
          if (child.tagName === 'SPAN' && child.textContent.trim()) return true;
        }

        // Also accept: a <label for="..."> anywhere on the page pointing to this input
        const id = el.id;
        if (id) {
          const lbl = document.querySelector(`label[for="${CSS.escape(id)}"]`);
          if (lbl && lbl.textContent.trim()) return true;
        }
        return false;
      }

      // ── Fallback (no TD ancestor): previous siblings in the same parent ──
      let sib = el.previousElementSibling;
      while (sib) {
        if (sib.tagName === 'SPAN' && sib.textContent.trim()) return true;
        if ([...sib.querySelectorAll('span')].some(s => s.textContent.trim())) return true;
        sib = sib.previousElementSibling;
      }
      const parent = el.parentElement;
      if (parent) {
        let psib = parent.previousElementSibling;
        while (psib) {
          if (psib.tagName === 'SPAN' && psib.textContent.trim()) return true;
          if ([...psib.querySelectorAll('span')].some(s => s.textContent.trim())) return true;
          psib = psib.previousElementSibling;
        }
      }
      const id = el.id;
      if (id) {
        const lbl = document.querySelector(`label[for="${CSS.escape(id)}"]`);
        if (lbl && lbl.textContent.trim()) return true;
      }
      return false;
    }

    // Get the text of preceding <td> cells in the same <tr> (before the td containing the input)
    function getPrecedingTdText(el) {
      const td = el.closest('td');
      if (!td) return '';
      const tr = td.parentElement;
      if (!tr) return '';
      const tds = [...tr.querySelectorAll('td')];
      const inputTdIdx = tds.indexOf(td);
      // Collect text from TDs before the input's TD
      return tds.slice(0, inputTdIdx).map(t => t.textContent.trim()).join(' ');
    }

    function eligibleInputs() {
      return Array.from(document.querySelectorAll('input, textarea, select')).filter(el => {
        if (el.tagName === 'INPUT') {
          const t = (el.type || 'text').toLowerCase();
          if (['hidden','submit','button','reset','file','image','checkbox','radio'].includes(t)) return false;
        }
        return true;
      });
    }

    // Finds every input whose [title] attribute contains the excel title
    // (needle), then orders them so ones with a preceding <span> (same <td>
    // as parent, span with text before the input) come first — the script
    // keeps searching ALL title matches to find the span-preceded one,
    // never stopping at the first title match it happens to encounter.
    // If NOTHING matches by title, falls back to checking the text of the
    // <td> cells preceding the input's <td> in the same row; in that case
    // plain DOM order is used ("the first input") with no span reordering.
    function findCandidates(title) {
      const needle = normText(title);
      if (!needle) return { candidates: [], mode: 'none' };

      const inputs = eligibleInputs();

      // Pass 1: match by title attribute
      const byTitle = inputs.filter(el => {
        const t = normText(el.getAttribute('title') || '');
        return t && t.includes(needle);
      });
      if (byTitle.length) {
        const withSpan    = byTitle.filter(hasPrecedingSpan);
        const withoutSpan = byTitle.filter(el => !hasPrecedingSpan(el));
        return { candidates: [...withSpan, ...withoutSpan], mode: 'title' };
      }

      // Pass 2: match by preceding <td> text in the same <tr> — plain DOM
      // order, no span prioritization (spec: replace the FIRST such input).
      const byTdText = inputs.filter(el => {
        const precedingText = normText(getPrecedingTdText(el));
        return precedingText && precedingText.includes(needle);
      });
      return { candidates: byTdText, mode: 'tdtext' };
    }

    const textarea  = win.querySelector('#__frsw_paste');
    const preview   = win.querySelector('#__frsw_preview');
    const resultEl  = win.querySelector('#__frsw_result');

    function refreshPreview() {
      const rows = parseLines(textarea.value);
      resultEl.textContent = '';
      if (!rows.length) { preview.innerHTML = ''; return; }

      const titleUsageCount = {};
      preview.innerHTML = rows.map(r => {
        const key = normText(r.title);
        const usageIdx = titleUsageCount[key] || 0;

        const { candidates } = findCandidates(r.title);

        const el = candidates[usageIdx] || null;
        titleUsageCount[key] = usageIdx + 1;

        const ok = !!el;
        const occLabel = usageIdx > 0 ? ` #${usageIdx + 1}` : '';
        const badge = ok
          ? `<span class="__frsw_row_badge">pole${occLabel}</span>`
          : `<span class="__frsw_row_badge miss">brak${occLabel}</span>`;
        return `<div class="__frsw_row ${ok ? '__frsw_row_match' : '__frsw_row_nomatch'}">
          <span class="__frsw_row_title">${r.title}</span>
          <span class="__frsw_row_arrow">→</span>
          <span class="__frsw_row_value">${r.value || '<em style="opacity:.5">puste</em>'}</span>
          ${badge}
        </div>`;
      }).join('');
    }

    textarea.addEventListener('input', refreshPreview);
    textarea.addEventListener('paste', () => setTimeout(refreshPreview, 0));

    win.querySelector('#__frsw_clear_ta').addEventListener('click', () => {
      textarea.value = '';
      preview.innerHTML = '';
      resultEl.textContent = '';
    });

    win.querySelector('#__frsw_apply').addEventListener('click', () => {
      const rows = parseLines(textarea.value);
      if (!rows.length) {
        resultEl.textContent = '⚠️ Brak danych do podstawienia.';
        resultEl.className = 'err';
        return;
      }

      // For duplicate titles: track how many times each title has been used
      // so the 2nd occurrence of "Color" fills the 2nd matching field, not the 1st again.
      const titleUsageCount = {};  // title.toLowerCase() → number of times already consumed
      const skipped = [];

      let filled = 0;
      rows.forEach(r => {
        const key = normText(r.title);
        const usageIdx = titleUsageCount[key] || 0;

        // findCandidates already orders matches correctly for the mode it
        // used: span-preceded inputs first when matched by [title], plain
        // DOM order ("first input") when matched by preceding <td> text.
        const { candidates } = findCandidates(r.title);

        if (usageIdx < candidates.length) {
          // Exactly ONE value gets written per excel row.
          setVal(candidates[usageIdx], r.value);
          titleUsageCount[key] = usageIdx + 1;
          filled++;
        } else {
          // No more fields for this title
          skipped.push(r.title);
        }
      });

      refreshPreview();

      let msg = `✅ Podstawiono ${filled} / ${rows.length} pól.`;
      let isErr = false;
      if (skipped.length) {
        const unique = [...new Set(skipped)];
        msg += `\n⚠️ Nie znaleziono kolejnego pola dla: ${unique.join(', ')}`;
        isErr = filled === 0;
      }
      resultEl.textContent = msg;
      resultEl.style.whiteSpace = 'pre-line';
      resultEl.className = isErr ? 'err' : '';

      if (filled) {
        const skipNote = skipped.length ? ` (${skipped.length} pominięto)` : '';
        showToast(`✏️ Schema: podstawiono ${filled} pole(i)${skipNote}`);
      } else {
        showToast('⚠️ Nie znaleziono pasujących pól', true);
      }
    });

    textarea.focus();
  };

  // ── Message listener ──────────────────────────────────────────────────────
  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    // Ping — just confirm script is alive
    if (msg.action === 'ping') { sendResponse({ ok: true }); return true; }

    // Form tool actions (from popup)
    if (msg.action === 'copyForms')      { window.__frCopyForms();       sendResponse({ ok: true }); return; }
    if (msg.action === 'pasteForms')     { window.__frPasteForms();      sendResponse({ ok: true }); return; }
    if (msg.action === 'clearForms')     { window.__frClearForms();      sendResponse({ ok: true }); return; }
    if (msg.action === 'unlockInputs')  { window.__frUnlockInputs();     sendResponse({ ok: true }); return; }
    if (msg.action === 'schemaWindow')  { window.__frOpenSchemaWindow(); sendResponse({ ok: true }); return; }

    // Find & Replace actions
    const prev = { ...state };
    if (msg.search        !== undefined) state.search        = msg.search;
    if (msg.replace       !== undefined) state.replace       = msg.replace;
    if (msg.caseSensitive !== undefined) state.caseSensitive = msg.caseSensitive;
    if (msg.wholeWord     !== undefined) state.wholeWord     = msg.wholeWord;
    if (msg.searchAll     !== undefined) state.searchAll     = msg.searchAll;

    const changed = state.search !== prev.search || state.caseSensitive !== prev.caseSensitive ||
                    state.wholeWord !== prev.wholeWord || state.searchAll !== prev.searchAll;

    switch (msg.action) {
      case 'find':    findAll(); break;
      case 'next':
        if (!state.matches.length || changed) findAll(); else navigate(1); break;
      case 'prev':
        if (!state.matches.length || changed) {
          findAll();
          if (state.matches.length > 1) { state.current = state.matches.length - 1; activateCurrent(); }
        } else navigate(-1);
        break;
      case 'replace':     if (!state.matches.length) findAll(); replaceCurrent(false); break;
      case 'replaceNext': if (!state.matches.length) findAll(); replaceCurrent(true);  break;
      case 'replaceAll':  replaceAll(); break;
      case 'getState':
        sendResponse({ search: state.search, replace: state.replace,
                       caseSensitive: state.caseSensitive, wholeWord: state.wholeWord,
                       searchAll: state.searchAll });
        return true;
    }
    sendResponse({ total: state.matches.length, current: state.current });
    return true;
  });
})();
