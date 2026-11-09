(function () {
  "use strict";
  var NIV = ["Irrelevante", "Opcional", "Importante", "Fundamental"], CLS = ["neutral", "amber", "blue", "good"];
  var $ = function (s, c) { return (c || document).querySelector(s); }, $$ = function (s, c) { return Array.prototype.slice.call((c || document).querySelectorAll(s)); };

  // Visibilidad de la contraseña sin enviar el formulario.
  $$("[data-password-toggle]").forEach(function (button) {
    var input = document.getElementById(button.getAttribute("aria-controls"));
    if (!input) return;
    button.hidden = false;
    button.addEventListener("click", function () {
      var visible = input.type === "password";
      input.type = visible ? "text" : "password";
      button.setAttribute("aria-pressed", String(visible));
      button.setAttribute("aria-label", visible ? "Ocultar contraseña" : "Mostrar contraseña");
    });
  });

  // Entrada escalonada de los hijos de [data-stagger] y de las filas de tablas.
  $$("[data-stagger]").forEach(function (box) { Array.prototype.forEach.call(box.children, function (el, i) { el.classList.add("reveal"); el.style.setProperty("--d", (0.06 * i + 0.05) + "s"); }); });
  $$("[data-stagger-rows] tr").forEach(function (tr, i) { tr.classList.add("reveal"); tr.style.setProperty("--d", Math.min(0.04 * i, 0.8) + "s"); });

  // Números que cuentan hacia arriba.
  $$("[data-count]").forEach(function (el) {
    var fin = parseFloat(el.getAttribute("data-count")) || 0, t0 = null, dur = 900;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) { el.textContent = fin; return; }
    function paso(t) { if (!t0) t0 = t; var p = Math.min((t - t0) / dur, 1), e = 1 - Math.pow(1 - p, 3); el.textContent = Math.round(fin * e); if (p < 1) requestAnimationFrame(paso); }
    requestAnimationFrame(paso);
  });

  // Barras y anillo: se animan al cargar.
  function barras() {
    $$("[data-w]").forEach(function (el) { el.style.width = el.getAttribute("data-w") + "%"; });
    $$("[data-h]").forEach(function (el) { el.style.height = el.getAttribute("data-h") + "%"; });
    $$(".ring-fg").forEach(function (el) { el.style.strokeDashoffset = 314 - 314 * (parseFloat(el.getAttribute("data-pct")) || 0) / 100; });
  }
  requestAnimationFrame(function () { setTimeout(barras, 120); });

  // Pestañas con línea deslizante.
  $$("[data-tabs]").forEach(function (tabs) {
    var line = $(".tab-line", tabs);
    function mover(b) { if (line && b) { line.style.left = b.offsetLeft + "px"; line.style.width = b.offsetWidth + "px"; } }
    $$("button", tabs).forEach(function (b) {
      b.addEventListener("click", function () {
        $$("button", tabs).forEach(function (x) { x.classList.toggle("on", x === b); });
        var cont = tabs.parentNode; $$("[data-panel]", cont).forEach(function (p) { p.classList.toggle("on", p.getAttribute("data-panel") === b.getAttribute("data-tab")); });
        mover(b);
      });
    });
    setTimeout(function () { mover($("button.on", tabs)); }, 60);
  });

  // Paso 1 y 2: importancia relativa y relevancia en vivo.
  var formImp = $("#formImp");
  if (formImp) {
    var recalcular = function (animar) {
      var rel = 0;
      $$("tr[data-sug]", formImp).forEach(function (tr) {
        var sel = $("input[type=radio]:checked", tr); if (!sel) return;
        var ir = Math.floor((parseInt(tr.getAttribute("data-sug"), 10) + parseInt(sel.value, 10)) / 2);
        var b = $(".badge.ir", tr), r = $(".badge.rel", tr);
        b.textContent = NIV[ir]; b.className = "badge ir " + CLS[ir];
        r.textContent = ir > 0 ? "Sí" : "No"; r.className = "badge rel " + (ir > 0 ? "good" : "bad");
        if (animar === tr) { b.classList.add("pulse"); setTimeout(function () { b.classList.remove("pulse"); }, 250); }
        if (ir > 0) rel++;
      });
      $("#relCount").textContent = rel;
    };
    formImp.addEventListener("change", function (e) { if (e.target.type === "radio") recalcular(e.target.closest("tr")); });
    recalcular();
  }

  // Paso 3 y 4: avance y ponderación media en vivo.
  var formSub = $("#formSub");
  if (formSub) {
    var cuenta = function () {
      var items = $$(".sublist li", formSub), hechos = 0, suma = 0;
      items.forEach(function (li) { var s = $("input:checked", li); if (s) { hechos++; suma += parseInt(s.value, 10); } });
      $("#subCount").textContent = hechos;
      $("#subBar").style.width = (items.length ? 100 * hechos / items.length : 0) + "%";
      $("#pmLive b").textContent = hechos ? (suma / hechos).toFixed(2) : "—";
    };
    formSub.addEventListener("change", cuenta); setTimeout(cuenta, 150);
  }

  // Confirmaciones, avisos, menú móvil y efecto de onda en botones.
  document.addEventListener("click", function (e) {
    var c = e.target.closest("[data-confirm]"); if (c && !window.confirm(c.getAttribute("data-confirm"))) { e.preventDefault(); return; }
    var btn = e.target.closest(".btn"); if (btn && !btn.disabled) {
      var r = document.createElement("span"), d = Math.max(btn.offsetWidth, btn.offsetHeight), box = btn.getBoundingClientRect();
      r.className = "ripple"; r.style.width = r.style.height = d + "px"; r.style.left = (e.clientX - box.left - d / 2) + "px"; r.style.top = (e.clientY - box.top - d / 2) + "px";
      btn.appendChild(r); setTimeout(function () { r.remove(); }, 600);
    }
  });
  $$(".toast").forEach(function (t, i) { setTimeout(function () { t.classList.add("out"); setTimeout(function () { t.remove(); }, 450); }, 5200 + i * 600); });
  var burger = $("#burger"); if (burger) burger.addEventListener("click", function () { $("#side").classList.toggle("open"); });
})();

/* Liquid glass: reflejo que sigue al puntero, barra de carga entre páginas, botones ocupados y ventanas modales. */
(function () {
  "use strict";
  var prog = document.getElementById("nav-progress"), raf = 0;
  function iniciar() { if (prog) prog.classList.add("on"); }
  window.addEventListener("pageshow", function () { if (prog) { prog.classList.remove("on"); } document.querySelectorAll(".btn.busy").forEach(function (b) { b.classList.remove("busy"); }); });
  document.addEventListener("click", function (e) {
    var o = e.target.closest("[data-open]");
    if (o) { var d = document.getElementById(o.getAttribute("data-open")); if (d && d.showModal) d.showModal(); return; }
    var c = e.target.closest("[data-close]"); if (c) { var dd = c.closest("dialog"); if (dd) dd.close(); return; }
    if (e.target.tagName === "DIALOG") { e.target.close(); return; }
    var a = e.target.closest("a[href]");
    if (a && !e.defaultPrevented && !e.metaKey && !e.ctrlKey && !e.shiftKey && a.target !== "_blank") {
      var h = a.getAttribute("href");
      if (h && h.charAt(0) !== "#" && h.indexOf("javascript") !== 0 && a.origin === location.origin && !a.hasAttribute("data-open")) iniciar();
    }
  });
  document.addEventListener("submit", function (e) {
    iniciar();
    var b = e.submitter; if (b && b.classList.contains("btn")) setTimeout(function () { b.classList.add("busy"); }, 0);
  });
  document.addEventListener("pointermove", function (e) {
    if (raf) return;
    raf = requestAnimationFrame(function () {
      raf = 0;
      var el = e.target.closest && e.target.closest(".card,.side,.top,.btn,.login-card"); if (!el) return;
      var r = el.getBoundingClientRect(); el.style.setProperty("--mx", (e.clientX - r.left) + "px"); el.style.setProperty("--my", (e.clientY - r.top) + "px");
    });
  }, { passive: true });
})();
