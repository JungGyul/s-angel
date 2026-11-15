/* S-ANGEL UI runtime
   - SA.toast(message, {type: 'success'|'error'|'warning'})
   - SA.confirm({title, message, confirmText, cancelText, danger}) → Promise<boolean>
   - SA.ajax(form, {onSuccess(data, form), confirm}) → fetch-based submit with JSON reply
   - <form data-confirm="..." [data-confirm-title] [data-confirm-ok] [data-danger]>
       → native forms get a confirm sheet before submitting.
   - <form data-busy> → submit button shows spinner after submit.
   - .table--stack → fills td[data-label] from the header row.
*/
(function () {
  "use strict";
  var SA = (window.SA = window.SA || {});
  var root = document.documentElement;

  /* ---------- toast ---------- */
  function toastRegion() {
    var r = document.getElementById("sa-toasts");
    if (!r) {
      r = document.createElement("div");
      r.id = "sa-toasts";
      r.className = "toasts";
      r.setAttribute("role", "status");
      r.setAttribute("aria-live", "polite");
      document.body.appendChild(r);
    }
    return r;
  }
  SA.toast = function (message, opts) {
    opts = opts || {};
    var type = opts.type || (opts.error ? "error" : "success");
    var icon = { success: "fa-circle-check", error: "fa-circle-exclamation", warning: "fa-triangle-exclamation", info: "fa-circle-info" }[type] || "fa-circle-check";
    var el = document.createElement("div");
    el.className = "toast glass toast--" + type;
    var i = document.createElement("i");
    i.className = "fa-solid " + icon;
    i.setAttribute("aria-hidden", "true");
    var span = document.createElement("span");
    span.textContent = message;
    el.append(i, span);
    var region = toastRegion();
    var dialogs = document.querySelectorAll("dialog[open]");
    var host = dialogs.length ? dialogs[dialogs.length - 1] : document.body;
    if (region.parentNode !== host) host.appendChild(region);
    region.appendChild(el);
    while (region.children.length > 3) region.firstElementChild.remove();
    setTimeout(function () {
      el.classList.add("is-leaving");
      setTimeout(function () { el.remove(); }, 260);
    }, opts.duration || 3200);
  };

  /* ---------- confirm sheet ---------- */
  SA.confirm = function (opts) {
    opts = typeof opts === "string" ? { message: opts } : opts || {};
    return new Promise(function (resolve) {
      if (typeof HTMLDialogElement !== "function") {
        resolve(window.confirm(opts.message || opts.title || "계속하시겠습니까?"));
        return;
      }
      var dlg = document.createElement("dialog");
      dlg.className = "sheet" + (opts.danger ? " sheet--danger" : "");
      dlg.setAttribute("aria-labelledby", "sa-sheet-title");
      dlg.innerHTML =
        '<div class="sheet__card glass">' +
        '<div class="sheet__icon"><i class="fa-solid ' + (opts.danger ? "fa-triangle-exclamation" : "fa-circle-question") + '" aria-hidden="true"></i></div>' +
        '<h2 class="sheet__title" id="sa-sheet-title"></h2>' +
        '<p class="sheet__text"></p>' +
        '<div class="sheet__actions">' +
        '<button type="button" class="btn btn--secondary" data-act="cancel"></button>' +
        '<button type="button" class="btn ' + (opts.danger ? "btn--danger" : "btn--primary") + '" data-act="ok"></button>' +
        "</div></div>";
      dlg.querySelector(".sheet__title").textContent = opts.title || "확인";
      var text = dlg.querySelector(".sheet__text");
      if (opts.message && opts.message !== opts.title) text.textContent = opts.message;
      else text.remove();
      dlg.querySelector('[data-act="cancel"]').textContent = opts.cancelText || "취소";
      dlg.querySelector('[data-act="ok"]').textContent = opts.confirmText || "확인";
      var prevFocus = document.activeElement;
      document.body.appendChild(dlg);
      var done = false;
      function close(val) {
        if (done) return;
        done = true;
        var region = document.getElementById("sa-toasts");
        if (region && dlg.contains(region)) document.body.appendChild(region);
        dlg.close();
        dlg.remove();
        if (prevFocus && prevFocus.focus && prevFocus.isConnected) prevFocus.focus();
        resolve(val);
      }
      dlg.addEventListener("click", function (e) {
        var act = e.target.closest("[data-act]");
        if (act) close(act.dataset.act === "ok");
        else if (e.target === dlg) close(false);
      });
      dlg.addEventListener("cancel", function (e) { e.preventDefault(); close(false); });
      dlg.showModal();
      dlg.querySelector(opts.danger ? '[data-act="cancel"]' : '[data-act="ok"]').focus();
    });
  };

  function confirmOptsFrom(el) {
    var msg = el.dataset.confirm;
    return {
      title: el.dataset.confirmTitle || msg,
      message: el.dataset.confirmTitle ? msg : "",
      confirmText: el.dataset.confirmOk || "확인",
      danger: el.hasAttribute("data-danger"),
    };
  }

  function setBusy(btn, busy) {
    if (!btn) return;
    if (busy) { btn.setAttribute("aria-busy", "true"); btn.disabled = true; }
    else { btn.removeAttribute("aria-busy"); btn.disabled = false; }
  }
  SA.setBusy = setBusy;

  /* ---------- fetch-based form submit ---------- */
  SA.ajax = function (form, opts) {
    opts = opts || {};
    form.addEventListener("submit", async function (event) {
      if (!window.fetch) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      if (form.dataset.confirm) {
        var ok = await SA.confirm(confirmOptsFrom(form));
        if (!ok) return;
      }
      var btn = event.submitter || form.querySelector('[type="submit"]');
      setBusy(btn, true);
      try {
        var response = await fetch(form.action, {
          method: "POST",
          body: new FormData(form),
          credentials: "same-origin",
          headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
        });
        var ct = response.headers.get("content-type") || "";
        if (!ct.includes("application/json")) {
          if (response.redirected) { window.location.assign(response.url); return; }
          throw new Error("bad response");
        }
        var data = await response.json();
        if (!response.ok || data.ok === false) {
          SA.toast(data.message || "요청을 처리하지 못했습니다.", { type: "error" });
          return;
        }
        if (opts.onSuccess) opts.onSuccess(data, form);
        if (data.message) SA.toast(data.message);
      } catch (e) {
        SA.toast("네트워크 상태를 확인한 뒤 다시 시도해 주십시오.", { type: "error" });
      } finally {
        if (btn && btn.isConnected) {
          setBusy(btn, false);
          if (document.activeElement === document.body || !document.activeElement) btn.focus({ preventScroll: true });
        }
      }
    });
  };

  /* ---------- global behaviours ---------- */
  document.addEventListener("submit", async function (event) {
    var form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    if (form.dataset.confirm && !form.dataset.confirmed) {
      event.preventDefault();
      var submitter = event.submitter;
      var ok = await SA.confirm(confirmOptsFrom(form));
      if (!ok) return;
      form.dataset.confirmed = "1";
      if (submitter && submitter.name) {
        var hidden = document.createElement("input");
        hidden.type = "hidden"; hidden.name = submitter.name; hidden.value = submitter.value;
        form.appendChild(hidden);
      }
      setBusy(submitter || form.querySelector('[type="submit"]'), true);
      HTMLFormElement.prototype.submit.call(form);
      return;
    }
    if (form.hasAttribute("data-busy") && !event.defaultPrevented) {
      var b = event.submitter || form.querySelector('[type="submit"]');
      setTimeout(function () { setBusy(b, true); }, 0);
    }
  });

  // links/buttons that need confirmation: <a data-confirm="..." href>
  document.addEventListener("click", async function (event) {
    var el = event.target.closest("a[data-confirm]");
    if (!el) return;
    event.preventDefault();
    if (await SA.confirm(confirmOptsFrom(el))) window.location.assign(el.href);
  });

  function labelTables() {
    document.querySelectorAll("table.table--stack").forEach(function (table) {
      var heads = Array.prototype.map.call(table.querySelectorAll("thead th"), function (th) { return th.textContent.trim(); });
      table.querySelectorAll("tbody tr").forEach(function (tr) {
        Array.prototype.forEach.call(tr.children, function (td, i) {
          if (!td.hasAttribute("data-label") && heads[i] !== undefined) td.setAttribute("data-label", heads[i]);
        });
      });
    });
  }
  SA.labelTables = labelTables;

  // close <details class="menu"> when clicking outside / pressing Escape
  document.addEventListener("click", function (e) {
    document.querySelectorAll("details.menu[open]").forEach(function (d) {
      if (!d.contains(e.target)) d.removeAttribute("open");
    });
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") document.querySelectorAll("details.menu[open]").forEach(function (d) { d.removeAttribute("open"); var sm = d.querySelector("summary"); if (sm) sm.focus(); });
  });

  /* ---------- app bar: condenses into a floating glass capsule as you scroll ----------
     Progress is tied 1:1 to scroll position (continuous, interruptible, no timers). */
  function bindAppbar() {
    var bar = document.querySelector(".appbar");
    if (!bar) return;
    var ticking = false, last = -1;
    function update() {
      ticking = false;
      var p = Math.min(1, Math.max(0, window.scrollY / 56));
      if (Math.abs(p - last) < 0.01) return;
      last = p;
      bar.style.setProperty("--p", p.toFixed(3));
      bar.classList.toggle("is-scrolled", p > 0.02);
    }
    window.addEventListener("scroll", function () {
      if (!ticking) { ticking = true; requestAnimationFrame(update); }
    }, { passive: true });
    update();
  }

  function init() {
    bindAppbar();
    labelTables();
    // Promote server messages flagged as toasts
    document.querySelectorAll("[data-toast]").forEach(function (el) {
      SA.toast(el.dataset.toast, { type: el.dataset.toastType || "success" });
      el.remove();
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
