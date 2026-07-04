/* Engineering Impact — static site. No framework, no external requests.
   All data arrives precomputed in window.__DATA__ (see scripts/build_site.py);
   this file only renders. Author names, rationales, and file paths are data,
   never markup: they enter the DOM via textContent only. */
(function () {
  "use strict";

  var D = window.__DATA__;
  var SIGNALS = D.signals;
  var AUTHORS = D.authors; // sorted by rank; index === rank - 1
  var byName = {};
  AUTHORS.forEach(function (a) { byName[a.name] = a; });

  var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function el(tag, className, text) {
    var n = document.createElement(tag);
    if (className) n.className = className;
    if (text !== undefined) n.textContent = text;
    return n;
  }
  function pctLabel(x) { return Math.round(x * 100) + "%"; }

  /* ---------------------------------------------------------- tooltip */
  var tip = document.getElementById("tooltip");
  function tipShow(lines, x, y) {
    // lines: [{v: strongValue, l: label}]; value leads, label follows.
    tip.textContent = "";
    lines.forEach(function (line) {
      var row = el("div");
      if (line.v !== undefined) row.appendChild(el("span", "tt-value", line.v + " "));
      if (line.l) row.appendChild(document.createTextNode(line.l));
      tip.appendChild(row);
    });
    tip.hidden = false;
    var pad = 14;
    var r = tip.getBoundingClientRect();
    var left = Math.min(x + pad, window.innerWidth - r.width - 8);
    var top = y - r.height - pad;
    if (top < 8) top = y + pad;
    tip.style.left = left + "px";
    tip.style.top = top + "px";
    tip.classList.add("show");
  }
  function tipHide() { tip.classList.remove("show"); tip.hidden = true; }

  /* --------------------------------------------------------- stat tiles */
  (function tiles() {
    var host = document.getElementById("stat-tiles");
    var items = [
      { label: "Contributors scored", value: String(D.meta.n_authors),
        sub: "Every non-bot author with commits in the window." },
      { label: "Data window", value: D.meta.window_label, small: true,
        sub: D.meta.n_commits.toLocaleString("en-US") + " non-merge commits, fixed window." },
      { label: "Review data", value: D.meta.review_status, small: true,
        sub: D.meta.review_status === "complete"
          ? "Fetch complete: absence of reviews is a true zero."
          : "Partial fetch: missing reviewers are median-imputed and badged." },
      { label: "Rank tiers", value: String(D.meta.n_tiers),
        sub: "Same tier = indistinguishable scores; within-tier order is not meaningful." }
    ];
    items.forEach(function (it) {
      var t = el("div", "tile");
      t.appendChild(el("div", "tile-label", it.label));
      t.appendChild(el("div", "tile-value" + (it.small ? " small" : ""), it.value));
      t.appendChild(el("div", "tile-sub", it.sub));
      host.appendChild(t);
    });
  })();

  /* ------------------------------------- signature: contributor field */
  (function field() {
    var NS = "http://www.w3.org/2000/svg";
    var F = D.field;
    var W = F.w, H = F.h, m = F.m;
    var pw = W - m.l - m.r, ph = H - m.t - m.b;
    var PX = function (nx) { return m.l + nx * pw; };
    var PY = function (ny) { return m.t + ny * ph; };

    var state = { view: "spectrum", signal: "own", filters: {} };

    var VIEWS = [
      { id: "spectrum", label: "Spectrum",
        coords: function (a) { return a.views.spectrum; },
        axis: { pct: true, xTitle: "impact score" } },
      { id: "activity", label: "Activity vs impact",
        coords: function (a) { return a.views.activity; },
        axis: { xTicks: F.x_ticks, yTicks: [0, 0.25, 0.5, 0.75, 1],
                xTitle: "commits — rejected baseline (log scale)",
                yTitle: "impact score", outliers: true } },
      { id: "signals", label: "Signals",
        coords: function (a) { return a.views[state.signal]; },
        axis: { pct: true, xTitle: "percentile within repo" } },
      { id: "tiers", label: "Tiers",
        coords: function (a) { return a.views.tiers; },
        axis: { tierTicks: F.tier_ticks, xTitle: "tier (1 = highest impact)" } }
    ];

    var svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label",
      "Every contributor as a dot. The leaderboard table carries the same data.");

    function svgEl(tag, attrs, cls, text) {
      var n = document.createElementNS(NS, tag);
      for (var k in attrs) n.setAttribute(k, attrs[k]);
      if (cls) n.setAttribute("class", cls);
      if (text !== undefined) n.textContent = text;
      return n;
    }

    // --- axis layers, one per view, prebuilt and crossfaded
    VIEWS.forEach(function (spec) {
      var g = svgEl("g", {}, "axis-layer" + (spec.id === state.view ? "" : " axis-hidden"));
      g.dataset.view = spec.id;
      g.appendChild(svgEl("line",
        { x1: m.l, x2: W - m.r, y1: PY(1), y2: PY(1) }, "baseline-l"));
      var ax = spec.axis;
      if (ax.pct) {
        [0, 0.25, 0.5, 0.75, 1].forEach(function (v) {
          g.appendChild(svgEl("text",
            { x: PX(v), y: PY(1) + 18, "text-anchor": "middle" }, "axis-tick",
            Math.round(v * 100) + "%"));
        });
      }
      (ax.xTicks || []).forEach(function (tk) {
        g.appendChild(svgEl("text",
          { x: PX(tk.x), y: PY(1) + 18, "text-anchor": "middle" }, "axis-tick",
          String(tk.v)));
      });
      (ax.tierTicks || []).forEach(function (tk) {
        g.appendChild(svgEl("text",
          { x: PX(tk.x), y: PY(1) + 18, "text-anchor": "middle" }, "axis-tick",
          "T" + tk.t));
      });
      (ax.yTicks || []).forEach(function (v) {
        if (v > 0) {
          g.appendChild(svgEl("line",
            { x1: m.l, x2: W - m.r, y1: PY(1 - v), y2: PY(1 - v) }, "gridline"));
        }
        g.appendChild(svgEl("text",
          { x: m.l - 8, y: PY(1 - v) + 3.5, "text-anchor": "end" }, "axis-tick",
          v.toFixed(2)));
      });
      if (ax.xTitle) {
        g.appendChild(svgEl("text",
          { x: m.l + pw / 2, y: H - 8, "text-anchor": "middle" }, "axis-title",
          ax.xTitle));
      }
      if (ax.yTitle) {
        g.appendChild(svgEl("text",
          { transform: "translate(14 " + (m.t + ph / 2) + ") rotate(-90)",
            "text-anchor": "middle" }, "axis-title", ax.yTitle));
      }
      svg.appendChild(g);
    });

    // --- dots: one pair of nodes per author, moved only via transform
    var points = [];
    AUTHORS.forEach(function (a) {
      var start = a.views.spectrum;
      var dot = svgEl("circle", { r: 4.5, cx: 0, cy: 0 }, "dot");
      var hit = svgEl("circle",
        { r: 10, cx: 0, cy: 0, tabindex: 0, role: "button" }, "dot-hit");
      hit.setAttribute("aria-label",
        a.name + " — impact " + a.impact.toFixed(3) + ", " + a.commits +
        " commits, rank " + a.rank + ", tier " + a.tier);
      var p = { a: a, dot: dot, hit: hit, dim: false,
                cx: PX(start[0]), cy: PY(0.5) };
      function place(x, y) {
        p.cx = x; p.cy = y;
        var t = "translate(" + x.toFixed(1) + " " + y.toFixed(1) + ")";
        dot.setAttribute("transform", t);
        hit.setAttribute("transform", t);
      }
      p.place = place;
      place(p.cx, p.cy);
      hit.addEventListener("focus", function () {
        dot.classList.add("hot");
        var box = hit.getBoundingClientRect();
        showPointTip(a, box.left + box.width / 2, box.top);
      });
      hit.addEventListener("blur", function () { dot.classList.remove("hot"); tipHide(); });
      hit.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); jumpToAuthor(a.name); }
      });
      svg.appendChild(dot);
      svg.appendChild(hit);
      points.push(p);
    });

    // --- outlier labels for the activity view (collision pass + leaders),
    // drawn above the dots and faded with that view
    var overlay = svgEl("g", {}, "axis-layer axis-hidden");
    overlay.dataset.view = "activity";
    (function activityLabels() {
      var labs = [];
      F.labeled.forEach(function (name) {
        var a = byName[name];
        if (a) labs.push({ name: name, cx: PX(a.views.activity[0]), cy: PY(a.views.activity[1]) });
      });
      labs.sort(function (p, q) { return p.cy - q.cy; });
      var prevBottom = -Infinity;
      labs.forEach(function (p) {
        var flip = p.cx > m.l + pw * 0.78;
        var ly = Math.max(p.cy + 3.5, prevBottom + 14);
        prevBottom = ly;
        if (ly - (p.cy + 3.5) > 5) {
          overlay.appendChild(svgEl("line",
            { x1: p.cx + (flip ? -6 : 6), y1: p.cy,
              x2: p.cx + (flip ? -8 : 8), y2: ly - 3.5 }, "leader"));
        }
        overlay.appendChild(svgEl("text",
          { x: p.cx + (flip ? -11 : 11), y: ly,
            "text-anchor": flip ? "end" : "start" }, "dot-label", p.name));
      });
    })();
    svg.appendChild(overlay);
    document.getElementById("field-svg").appendChild(svg);

    // SIGNALS is in [ownership, survival, coupling, review] order
    var VIEW_SIGNAL = {
      own: SIGNALS[0], surv: SIGNALS[1], coup: SIGNALS[2], rev: SIGNALS[3]
    };
    function showPointTip(a, x, y) {
      var line2 = a.commits + " commits · rank " + a.rank + " · tier " + a.tier;
      if (state.view === "signals") {
        var s = VIEW_SIGNAL[state.signal];
        line2 = s.label + " " + pctLabel(a.signals[s.key]) + " · " + line2;
      }
      tipShow([{ v: a.impact.toFixed(3), l: a.name }, { l: line2 }], x, y);
    }

    // --- one rAF tween for all dots; retargets cleanly mid-flight
    var anim = null;
    function retarget() {
      var spec = VIEWS.filter(function (v) { return v.id === state.view; })[0];
      var targets = points.map(function (p) {
        var c = spec.coords(p.a);
        return { p: p, x0: p.cx, y0: p.cy, x1: PX(c[0]), y1: PY(c[1]) };
      });
      if (reducedMotion) {
        targets.forEach(function (t) { t.p.place(t.x1, t.y1); });
        return;
      }
      if (anim) cancelAnimationFrame(anim);
      var t0 = performance.now(), DUR = 420;
      (function frame(now) {
        var t = Math.min((now - t0) / DUR, 1);
        var e = 1 - Math.pow(1 - t, 3);
        targets.forEach(function (tg) {
          tg.p.place(tg.x0 + (tg.x1 - tg.x0) * e, tg.y0 + (tg.y1 - tg.y0) * e);
        });
        anim = t < 1 ? requestAnimationFrame(frame) : null;
      })(t0);
    }

    // --- nearest-point pointer layer (skips dimmed dots; focus never does)
    var hotPoint = null;
    function nearestPoint(ev) {
      var box = svg.getBoundingClientRect();
      var sx = (ev.clientX - box.left) * W / box.width;
      var sy = (ev.clientY - box.top) * H / box.height;
      var best = null, bestD = Infinity;
      points.forEach(function (p) {
        if (p.dim) return;
        var d = (p.cx - sx) * (p.cx - sx) + (p.cy - sy) * (p.cy - sy);
        if (d < bestD) { bestD = d; best = p; }
      });
      if (!best) return null;
      var px = Math.sqrt(bestD) * box.width / W;
      return px <= 32 ? best : null;
    }
    svg.addEventListener("pointermove", function (ev) {
      var p = nearestPoint(ev);
      if (p !== hotPoint) {
        if (hotPoint) hotPoint.dot.classList.remove("hot");
        hotPoint = p;
        if (p) p.dot.classList.add("hot");
      }
      if (p) { svg.style.cursor = "pointer"; showPointTip(p.a, ev.clientX, ev.clientY); }
      else { svg.style.cursor = ""; tipHide(); }
    });
    svg.addEventListener("pointerleave", function () {
      if (hotPoint) { hotPoint.dot.classList.remove("hot"); hotPoint = null; }
      tipHide();
    });
    svg.addEventListener("click", function (ev) {
      var p = nearestPoint(ev);
      if (p) jumpToAuthor(p.a.name);
    });

    // --- controls: view radiogroup, signal radiogroup, filter chips
    function radiogroup(host, items, isChecked, onPick) {
      var buttons = items.map(function (it) {
        var b = el("button", null, it.label);
        b.type = "button";
        b.setAttribute("role", "radio");
        b.dataset.id = it.id;
        b.addEventListener("click", function () { onPick(it.id); });
        host.appendChild(b);
        return b;
      });
      host.addEventListener("keydown", function (ev) {
        if (ev.key !== "ArrowRight" && ev.key !== "ArrowLeft") return;
        ev.preventDefault();
        var i = buttons.indexOf(document.activeElement);
        var j = (i + (ev.key === "ArrowRight" ? 1 : -1) + buttons.length) % buttons.length;
        buttons[j].focus();
        buttons[j].click();
      });
      function sync() {
        buttons.forEach(function (b) {
          var on = isChecked(b.dataset.id);
          b.setAttribute("aria-checked", on ? "true" : "false");
          b.tabIndex = on ? 0 : -1;
        });
      }
      sync();
      return sync;
    }

    var signalHost = document.getElementById("field-signal");
    var syncViews = radiogroup(
      document.getElementById("field-views"), VIEWS,
      function (id) { return id === state.view; },
      function (id) {
        state.view = id;
        syncViews();
        signalHost.hidden = id !== "signals";
        svg.querySelectorAll(".axis-layer").forEach(function (g) {
          g.classList.toggle("axis-hidden", g.dataset.view !== id);
        });
        document.querySelectorAll(".field-caption p").forEach(function (cap) {
          cap.hidden = cap.dataset.view !== id;
        });
        retarget();
      });

    var SIGNAL_VIEWS = [
      { id: "own", label: "Ownership" }, { id: "surv", label: "Survival" },
      { id: "coup", label: "Coupling" }, { id: "rev", label: "Reviews" }
    ];
    var syncSignals = radiogroup(signalHost, SIGNAL_VIEWS,
      function (id) { return id === state.signal; },
      function (id) { state.signal = id; syncSignals(); retarget(); });

    var CHIPS = [
      { id: "bus", glyph: "⚠", label: "bus-factor",
        test: function (a) { return a.flags.bus_factor; } },
      { id: "rev", glyph: "", label: "gave reviews",
        test: function (a) { return a.review && a.review.count > 0; } },
      { id: "norev", glyph: "◌", label: "no review data",
        test: function (a) { return a.flags.review_imputed; } }
    ];
    var countEl = document.getElementById("field-count");
    var chipHost = document.getElementById("field-filters");
    CHIPS.forEach(function (c) {
      c.count = AUTHORS.filter(c.test).length;
      var b = el("button", "chip-toggle");
      b.type = "button";
      b.setAttribute("aria-pressed", "false");
      if (c.glyph) b.appendChild(el("span", "warn-glyph", c.glyph + " "));
      b.appendChild(document.createTextNode(c.label + " · " + c.count));
      b.addEventListener("click", function () {
        state.filters[c.id] = !state.filters[c.id];
        b.setAttribute("aria-pressed", state.filters[c.id] ? "true" : "false");
        applyFilters();
      });
      chipHost.appendChild(b);
    });
    function applyFilters() {
      var active = CHIPS.filter(function (c) { return state.filters[c.id]; });
      var n = 0;
      points.forEach(function (p) {
        var match = !active.length ||
          active.some(function (c) { return c.test(p.a); });
        p.dim = active.length > 0 && !match;
        p.dot.classList.toggle("dim", p.dim);
        p.hit.classList.toggle("dim", p.dim);
        if (match) n += 1;
      });
      countEl.textContent = active.length ? n + " / " + AUTHORS.length : "";
    }
    applyFilters();

    // opening bloom: dots start on the axis line and swarm into place
    retarget();
  })();

  /* ----------------------------------------------------------- leaderboard */
  var body = document.getElementById("board-body");
  var search = document.getElementById("search");
  var rowCount = document.getElementById("row-count");
  var state = { key: "rank", dir: 1, query: "" };
  var openName = null;

  function accessor(key) {
    if (key === "rank") return function (a) { return a.rank; };
    if (key === "name") return function (a) { return a.name.toLowerCase(); };
    if (key === "impact") return function (a) { return a.impact; };
    return function (a) { return a.signals[key]; };
  }

  function visibleAuthors() {
    var q = state.query.trim().toLowerCase();
    var list = AUTHORS.filter(function (a) {
      return !q || a.name.toLowerCase().indexOf(q) !== -1;
    });
    var get = accessor(state.key);
    list = list.slice().sort(function (a, b) {
      var va = get(a), vb = get(b);
      var c = va < vb ? -1 : va > vb ? 1 : a.rank - b.rank;
      return c * state.dir;
    });
    return list;
  }

  function microBar(pct, imputed, wide) {
    var wrap = el("div", wide ? "cbar" : "sig-wrap");
    var track = el("div", "track");
    var fill = el("div", "fill" + (imputed ? " imputed" : ""));
    fill.style.width = (pct * 100).toFixed(1) + "%";
    track.appendChild(fill);
    wrap.appendChild(track);
    if (wide) wrap.appendChild(el("span", "val", pct.toFixed(3)));
    return wrap;
  }

  function buildRow(a) {
    var tr = el("tr", "row");
    tr.tabIndex = 0;
    tr.dataset.name = a.name;
    tr.setAttribute("aria-expanded", "false");

    var rank = el("td", "num", String(a.rank));
    var name = el("td", "name-cell", a.name);
    name.appendChild(el("span", "tier-chip", "T" + a.tier));
    if (a.github) {
      var gh = el("a", "gh-link", "↗");
      gh.href = "https://github.com/" + encodeURIComponent(a.github);
      gh.target = "_blank";
      gh.rel = "noopener noreferrer";
      gh.setAttribute("aria-label", a.name + " on GitHub");
      gh.addEventListener("click", function (ev) { ev.stopPropagation(); });
      name.appendChild(gh);
    }
    var impact = el("td", "w-impact");
    impact.appendChild(microBar(a.impact, false, true));
    tr.appendChild(rank); tr.appendChild(name); tr.appendChild(impact);

    SIGNALS.forEach(function (s) {
      var td = el("td", "sig");
      td.appendChild(microBar(a.signals[s.key], s.key === "review_leverage" && a.flags.review_imputed, false));
      tr.appendChild(td);
    });

    var flags = el("td", "w-flags");
    if (a.flags.bus_factor) flags.appendChild(el("span", "badge badge-warn", "⚠ bus-factor"));
    if (a.flags.review_imputed) {
      if (flags.firstChild) flags.appendChild(document.createTextNode(" "));
      flags.appendChild(el("span", "badge badge-mut", "◌ no review data"));
    }
    tr.appendChild(flags);

    tr.addEventListener("click", function () { toggleDetail(tr, a); });
    tr.addEventListener("keydown", function (ev) {
      if (ev.target !== tr) return; // e.g. Enter on the GitHub anchor
      if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); toggleDetail(tr, a); }
      if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
        ev.preventDefault();
        var rows = Array.prototype.slice.call(body.querySelectorAll("tr.row"));
        var i = rows.indexOf(tr) + (ev.key === "ArrowDown" ? 1 : -1);
        if (rows[i]) rows[i].focus();
      }
    });
    return tr;
  }

  function render() {
    body.textContent = "";
    openName = null;
    var list = visibleAuthors();
    var defaultOrder = state.key === "rank" && state.dir === 1 && !state.query.trim();
    var lastTier = null;
    list.forEach(function (a) {
      // Divider rows only where they say something: a shared tier means the
      // scores are indistinguishable and within-tier order must not be read.
      // Singleton tiers carry their tier in the row chip instead.
      if (defaultOrder && a.tier !== lastTier) {
        lastTier = a.tier;
        var tierInfo = D.tiers[a.tier - 1];
        if (tierInfo.count > 1) {
          var tr = el("tr", "tier-row");
          var td = el("td", null,
            "tier " + a.tier + " — " + tierInfo.count +
            " contributors, indistinguishable within epsilon");
          td.colSpan = 8;
          tr.appendChild(td);
          body.appendChild(tr);
        }
      }
      body.appendChild(buildRow(a));
    });
    rowCount.textContent = list.length + " / " + AUTHORS.length;
    document.querySelectorAll(".board thead th[data-sort]").forEach(function (th) {
      if (th.dataset.sort === state.key) {
        th.setAttribute("aria-sort", state.dir === 1 ? "ascending" : "descending");
      } else {
        th.removeAttribute("aria-sort");
      }
    });
  }

  document.querySelectorAll(".board thead th[data-sort]").forEach(function (th) {
    th.querySelector("button").addEventListener("click", function () {
      var key = th.dataset.sort;
      if (state.key === key) {
        state.dir = -state.dir;
      } else {
        state.key = key;
        state.dir = (key === "rank" || key === "name") ? 1 : -1; // scores default high→low
      }
      render();
    });
  });

  search.addEventListener("input", function () {
    state.query = search.value;
    render();
  });

  /* ------------------------------------------------------------- detail */
  function closeDetail() {
    var open = body.querySelector("tr.detail.open");
    if (open) {
      open.classList.remove("open");
      var row = open.previousSibling;
      if (row && row.classList) row.setAttribute("aria-expanded", "false");
    }
    openName = null;
  }

  function toggleDetail(tr, a) {
    var next = tr.nextSibling;
    var isOpen = next && next.classList && next.classList.contains("detail") &&
                 next.classList.contains("open");
    closeDetail();
    if (isOpen) return;
    var detail = (next && next.classList && next.classList.contains("detail"))
      ? next : insertDetail(tr, a);
    // force layout so the 0fr -> 1fr transition runs on first open
    void detail.offsetHeight;
    detail.classList.add("open");
    tr.setAttribute("aria-expanded", "true");
    openName = a.name;
    detail.querySelectorAll(".dbar .fill").forEach(function (f) {
      f.style.width = f.dataset.w;
    });
  }

  function insertDetail(tr, a) {
    var dtr = el("tr", "detail");
    var td = el("td");
    td.colSpan = 8;
    var clip = el("div", "detail-clip");
    var inner = el("div", "detail-inner");
    var grid = el("div", "detail-body");

    var rationale = el("p", "rationale", a.rationale);
    rationale.style.gridColumn = "1 / -1";
    rationale.style.margin = "0";
    grid.appendChild(rationale);

    // left: signals + review reach + shown-not-scored context
    var left = el("div");
    left.appendChild(el("h4", "detail-h", "Signal percentiles"));
    SIGNALS.forEach(function (s) {
      var imputed = s.key === "review_leverage" && a.flags.review_imputed;
      var bar = el("div", "dbar");
      var lbl = el("span", "lbl", s.label + " ");
      if (imputed) lbl.appendChild(el("small", null, "median-imputed"));
      var track = el("div", "track");
      var fill = el("div", "fill" + (imputed ? " imputed" : ""));
      fill.dataset.w = (a.signals[s.key] * 100).toFixed(1) + "%";
      if (reducedMotion) fill.style.width = fill.dataset.w;
      track.appendChild(fill);
      bar.appendChild(lbl);
      bar.appendChild(track);
      bar.appendChild(el("span", "val", pctLabel(a.signals[s.key])));
      left.appendChild(bar);
    });

    var rl = el("p", "review-line");
    if (a.review) {
      rl.appendChild(document.createTextNode("Reviews given: "));
      rl.appendChild(el("strong", null, String(a.review.count)));
      rl.appendChild(document.createTextNode(" across "));
      rl.appendChild(el("strong", null, String(a.review.distinct_authors)));
      rl.appendChild(document.createTextNode(
        " distinct authors · approval rate " + Math.round(a.review.approval_rate * 100) +
        "% (context, not scored)"));
    } else {
      rl.textContent = "No PR reviews on record for this contributor.";
    }
    left.appendChild(rl);

    if (a.github) {
      var ghp = el("p", "review-line");
      var ghd = el("a", "gh-detail");
      ghd.href = "https://github.com/" + encodeURIComponent(a.github);
      ghd.target = "_blank";
      ghd.rel = "noopener noreferrer";
      ghd.textContent = "github.com/" + a.github + " ↗";
      ghp.appendChild(ghd);
      left.appendChild(ghp);
    }

    var chips = el("div", "chips");
    [["files touched", a.aux.breadth_files],
     ["directories", a.aux.breadth_dirs],
     ["days since last commit", a.aux.recency_days],
     ["consistency", a.aux.consistency.toFixed(2)]].forEach(function (c) {
      var chip = el("span", "chip");
      chip.appendChild(el("b", null, String(c[1])));
      chip.appendChild(document.createTextNode(" " + c[0]));
      chips.appendChild(chip);
    });
    chips.appendChild(el("span", "chip", "shown, not scored"));
    left.appendChild(chips);

    if (a.weekly && a.weekly.some(function (w) { return w > 0; })) {
      var sw = el("div", "spark-wrap");
      sw.appendChild(sparkline(a.weekly));
      sw.appendChild(el("div", "spark-cap",
        "Commits per week over the data window · peak " + Math.max.apply(null, a.weekly)));
      left.appendChild(sw);
    }
    grid.appendChild(left);

    // right: owned files by centrality
    var right = el("div");
    right.appendChild(el("h4", "detail-h", "Highest-centrality owned files"));
    if (a.top_files.length) {
      var table = el("table", "files-table");
      var thead = el("thead");
      var hr = el("tr");
      ["File", "Blame", "Centrality", ""].forEach(function (h) {
        hr.appendChild(el("th", null, h));
      });
      thead.appendChild(hr);
      table.appendChild(thead);
      var tbody = el("tbody");
      var maxC = Math.max.apply(null, a.top_files.map(function (f) { return f.centrality; })) || 1;
      a.top_files.forEach(function (f) {
        var r = el("tr");
        var p = el("td", "fpath", middleTruncate(f.path, 42));
        p.title = f.path;
        r.appendChild(p);
        r.appendChild(el("td", "fnum", pctLabel(f.blame_share)));
        var cb = el("td", "fbar");
        var track = el("div", "track");
        var fill = el("div", "fill");
        fill.style.width = (f.centrality / maxC * 100).toFixed(1) + "%";
        track.appendChild(fill);
        cb.appendChild(track);
        r.appendChild(cb);
        var dot = el("td");
        if (f.orphan) {
          var d = el("span", "owner-dot");
          d.title = "single-owner file";
          dot.appendChild(d);
        }
        r.appendChild(dot);
        tbody.appendChild(r);
      });
      table.appendChild(tbody);
      right.appendChild(table);
      right.appendChild(el("p", "files-note",
        "● single-owner: no other major contributor — the orphan-risk side of ownership."));
    } else {
      right.appendChild(el("p", "review-line",
        "No surviving major-owned files at HEAD."));
    }
    grid.appendChild(right);

    inner.appendChild(grid);
    clip.appendChild(inner);
    td.appendChild(clip);
    dtr.appendChild(td);
    tr.parentNode.insertBefore(dtr, tr.nextSibling);
    return dtr;
  }

  function middleTruncate(s, max) {
    if (s.length <= max) return s;
    var keep = Math.floor((max - 1) / 2);
    return s.slice(0, keep) + "…" + s.slice(s.length - keep);
  }

  function sparkline(weekly) {
    var w = 460, h = 40, pad = 2;
    var max = Math.max.apply(null, weekly) || 1;
    var n = weekly.length;
    var pts = weekly.map(function (v, i) {
      var x = pad + i * (w - 2 * pad) / Math.max(n - 1, 1);
      var y = h - pad - v / max * (h - 2 * pad);
      return x.toFixed(1) + "," + y.toFixed(1);
    });
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 " + w + " " + h);
    svg.setAttribute("preserveAspectRatio", "none");
    svg.setAttribute("aria-hidden", "true");
    var area = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
    area.setAttribute("class", "spark-area");
    area.setAttribute("points",
      pad + "," + (h - pad) + " " + pts.join(" ") + " " + (w - pad) + "," + (h - pad));
    var line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
    line.setAttribute("class", "spark-line");
    line.setAttribute("points", pts.join(" "));
    svg.appendChild(area);
    svg.appendChild(line);
    return svg;
  }

  function jumpToAuthor(name) {
    if (state.query) { state.query = ""; search.value = ""; }
    if (state.key !== "rank" || state.dir !== 1) { state.key = "rank"; state.dir = 1; }
    render();
    var row = body.querySelector('tr.row[data-name="' + cssEscape(name) + '"]');
    if (!row) return;
    toggleDetail(row, byName[name]);
    row.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "center" });
    row.focus({ preventScroll: true });
  }
  function cssEscape(s) {
    return (window.CSS && CSS.escape) ? CSS.escape(s) : s.replace(/["\\]/g, "\\$&");
  }

  /* ------------------------------------------------------------ scroll spy */
  (function spy() {
    var links = {};
    document.querySelectorAll(".nav-links a").forEach(function (a) {
      links[a.getAttribute("href").slice(1)] = a;
    });
    var current = null;
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        if (current) current.classList.remove("active");
        current = links[e.target.id] || null;
        if (current) current.classList.add("active");
      });
    }, { rootMargin: "-30% 0px -60% 0px" });
    Object.keys(links).forEach(function (id) {
      var s = document.getElementById(id);
      if (s) io.observe(s);
    });
  })();

  /* ------------------------------------------------------- global keyboard */
  document.addEventListener("keydown", function (ev) {
    var typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
    if (ev.key === "/" && !typing) {
      ev.preventDefault();
      search.focus();
    } else if (ev.key === "Escape") {
      if (typing && search.value) {
        search.value = ""; state.query = ""; render();
      } else {
        closeDetail();
      }
      tipHide();
    }
  });

  render();
})();
