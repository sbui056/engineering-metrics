/* Engineering Impact — static site. No framework, no external requests.
   All data arrives precomputed in window.__DATA__ (see scripts/build_site.py);
   this file only renders. Author names, rationales, and file paths are data,
   never markup: they enter the DOM via textContent only. */
(function () {
  "use strict";

  // arms the reveal/motion CSS; without JS the page renders fully visible
  document.documentElement.classList.add("js");

  var D = window.__DATA__;
  var SIGNALS = D.signals;
  var AUTHORS = D.authors; // sorted by rank; index === rank - 1
  var byName = {};
  AUTHORS.forEach(function (a) { byName[a.name] = a; });

  var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // fixed signal colors (validated categorical set — see styles.css tokens);
  // identity is carried consistently: formula, minibars, detail bars, icons
  var SIG_COLORS = {
    ownership_concentration: "#D64A22",
    code_survival_tenure_normalized: "#2E8B61",
    coupling_criticality: "#3563C9",
    review_leverage: "#A34981"
  };

  function el(tag, className, text) {
    var n = document.createElement(tag);
    if (className) n.className = className;
    if (text !== undefined) n.textContent = text;
    return n;
  }
  function pctLabel(x) { return Math.round(x * 100) + "%"; }
  function plural(n, word) { return n + " " + word + (n === 1 ? "" : "s"); }
  function ordinal(n) {
    var m100 = n % 100, m10 = n % 10;
    if (m100 >= 11 && m100 <= 13) return n + "th";
    return n + (m10 === 1 ? "st" : m10 === 2 ? "nd" : m10 === 3 ? "rd" : "th");
  }

  // one signal percentile bar, shared by the detail panel and the compare
  // dialog. The caller sets --w from fill.dataset.w after insertion so the
  // grow animation runs on open; reduced motion fills immediately. opts.lead
  // appends a neutral "leads" tag (compare marks where each side is higher —
  // never a winner: "signals, not verdicts").
  function signalBar(a, s, opts) {
    opts = opts || {};
    var imputed = s.key === "review_leverage" && a.flags.review_imputed;
    var bar = el("div", "dbar");
    var lbl = el("span", "lbl", (opts.short && s.short ? s.short : s.label) + " ");
    if (imputed) lbl.appendChild(el("small", null, "median-imputed"));
    var track = el("div", "track");
    var fill = el("div", "fill" + (imputed ? " imputed" : ""));
    fill.style.setProperty("--sig-color", SIG_COLORS[s.key]);
    if (!imputed) fill.style.background = SIG_COLORS[s.key];
    fill.dataset.w = (a.signals[s.key] * 100).toFixed(1) + "%";
    if (reducedMotion) fill.style.setProperty("--w", fill.dataset.w);
    track.appendChild(fill);
    bar.appendChild(lbl);
    bar.appendChild(track);
    bar.appendChild(el("span", "val", pctLabel(a.signals[s.key])));
    if (opts.lead) bar.appendChild(el("span", "leads", "leads"));
    return bar;
  }

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

  /* ------------------------------------------------------- stat cells */
  (function tiles() {
    var host = document.getElementById("stat-tiles");
    var items = [
      { label: "Contributors scored", value: String(D.meta.n_authors), count: D.meta.n_authors,
        sub: "Every non-bot author with commits in the window." },
      { label: "Non-merge commits", value: D.meta.n_commits.toLocaleString("en-US"),
        count: D.meta.n_commits, sub: "Fixed window: " + D.meta.window_label + "." },
      { label: "Review data", value: D.meta.review_status, small: true,
        sub: D.meta.review_status === "complete"
          ? "Fetch complete: absence of reviews is a true zero."
          : "Partial fetch: missing reviewers are median-imputed and badged." },
      { label: "Rank tiers", value: String(D.meta.n_tiers), count: D.meta.n_tiers,
        sub: "Same tier = indistinguishable scores; within-tier order is not meaningful." }
    ];
    items.forEach(function (it, i) {
      var t = el("div", "tile");
      t.setAttribute("data-reveal", "");
      t.style.setProperty("--d", i * 60 + "ms");
      var v = el("div", "tile-value" + (it.small ? " small" : ""), it.value);
      if (it.count !== undefined) {
        v.dataset.count = String(it.count);
        v.dataset.text = it.value;
      }
      t.appendChild(v);
      t.appendChild(el("div", "tile-label", it.label));
      t.appendChild(el("div", "tile-sub", it.sub));
      host.appendChild(t);
    });
  })();

  /* ------------------------------------------------- card header stat
     the page's ONE odometer: per-digit clip-mask rolls, fast, instrument-
     styled. Finishes (and beforeprint-forces) to plain text in the DOM. */
  (function fieldStat() {
    var host = document.getElementById("field-stat");
    if (!host || !AUTHORS.length) return;
    var target = AUTHORS[0].impact;
    var text = target.toFixed(3);
    var v = el("div", "v", text);
    var s = el("small", null, "top score · tier 1 of " + D.meta.n_tiers);
    host.appendChild(v);
    host.appendChild(s);
    if (reducedMotion || !("IntersectionObserver" in window)) return;
    // build the digit columns (non-digits pass through as static chars)
    var done = false;
    function finalize() {
      if (done) return;
      done = true;
      v.textContent = text;
      v.removeAttribute("aria-label");
    }
    v.textContent = "";
    v.setAttribute("aria-label", text);
    var cols = [];
    text.split("").forEach(function (ch, i) {
      if (!/\d/.test(ch)) {
        v.appendChild(el("span", "odo-static", ch));
        return;
      }
      var d = el("span", "odo-d");
      var col = el("span", "odo-col");
      for (var n = 0; n <= 9; n++) col.appendChild(el("span", "odo-n", String(n)));
      col.style.setProperty("--od", String(cols.length));
      d.appendChild(col);
      v.appendChild(d);
      cols.push({ col: col, digit: +ch });
    });
    var io = new IntersectionObserver(function (entries) {
      if (!entries.some(function (e) { return e.isIntersecting; })) return;
      io.disconnect();
      requestAnimationFrame(function () {
        cols.forEach(function (c) {
          c.col.style.transform = "translateY(" + (-c.digit) + "em)";
        });
      });
      var last = cols[cols.length - 1];
      if (!last) { finalize(); return; }
      last.col.addEventListener("transitionend", finalize, { once: true });
      setTimeout(finalize, 1400); // safety net if transitions are killed
    }, { threshold: 0.3 });
    io.observe(host);
    window.addEventListener("beforeprint", finalize);
  })();

  /* ------------------------------------- signature: contributor field */
  var highlightDot = null;  // set by the field; used by the leaderboard detail
  var setFieldView = null;  // set by the field; used by hash-state routing
  var hashSetC = null;      // set by the hash module; used by tap-to-pin
  var onFieldViewChange = null; // set by the hash module; called from setView
  var fieldRetarget = null; // set by the field; used by the weight-mixer lab
  var fieldGravity = null;  // set by the field; the "gravity" easter-egg toggle
  var compareToggle = null; // set by compare; used by buildRow's ⇄ button
  var compareHas = null;    // set by compare; buildRow marks selected rows
  var compareGetPair = null;// set by compare; read by hashState.serialize (#cmp)
  var compareApply = null;  // set by compare; called by hashState on a #cmp deep-link
  var compareClose = null;  // set by compare; called by the global Escape handler
  var orgSimSet = null;     // set by orgLens; row ⚠ badges preselect the sim through here
  // weight-mixer state (null = shipped scoring): {score, rank} maps by name.
  // mixScores additionally bends the spectrum view's x inside retarget().
  var mixLab = null;
  var mixScores = null;
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
      { id: "activity", label: "Activity vs impact", short: "Activity",
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
    svg.setAttribute("role", "group"); // not "img": it contains focusable dot targets
    svg.setAttribute("aria-label",
      "Every contributor as a dot. The leaderboard table carries the same data.");

    function svgEl(tag, attrs, cls, text) {
      var n = document.createElementNS(NS, tag);
      for (var k in attrs) n.setAttribute(k, attrs[k]);
      if (cls) n.setAttribute("class", cls);
      if (text !== undefined) n.textContent = text;
      return n;
    }

    // rank percentile drives dot radius and ramp color.
    // Ramp matches --ramp in the stylesheet (validated ordinal, see tokens).
    var RAMP = ["#EC9E74", "#DF7647", "#CB5124", "#A63C15", "#78290C"];
    var N = AUTHORS.length;
    function impactPct(a) { return N > 1 ? 1 - (a.rank - 1) / (N - 1) : 1; }
    function rampColor(t) {
      t = Math.max(0, Math.min(1, t)) * (RAMP.length - 1);
      var i = Math.min(Math.floor(t), RAMP.length - 2), f = t - i;
      function chan(hex, o) { return parseInt(hex.substr(o, 2), 16); }
      var c = [1, 3, 5].map(function (o) {
        return Math.round(chan(RAMP[i], o) + (chan(RAMP[i + 1], o) - chan(RAMP[i], o)) * f);
      });
      return "rgb(" + c.join(",") + ")";
    }
    // radius tuned at N=82; the build scales it down for larger cohorts
    var RSCALE = F.rscale || 1;
    function dotRadius(pct) { return (4 + 4.8 * Math.pow(pct, 1.5)) * RSCALE; }


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
      if (spec.id === "spectrum" && AUTHORS.length > 3) {
        // dashed ink median + white chip (the reference's annotation device)
        var imps = AUTHORS.map(function (a) { return a.impact; })
          .sort(function (x, y) { return x - y; });
        var mid = imps.length % 2
          ? imps[(imps.length - 1) / 2]
          : (imps[imps.length / 2 - 1] + imps[imps.length / 2]) / 2;
        var mx = PX(mid);
        var label = "median " + mid.toFixed(3);
        var chipW = label.length * 8.2 + 22;
        var chipX = Math.min(Math.max(mx - chipW / 2, m.l + 4), W - m.r - chipW - 4);
        g.appendChild(svgEl("line",
          { x1: mx, x2: mx, y1: m.t + 40, y2: PY(1) }, "median-line"));
        g.appendChild(svgEl("rect",
          { x: chipX, y: m.t + 6, width: chipW, height: 26, rx: 13 }, "median-chip-box"));
        g.appendChild(svgEl("text",
          { x: chipX + chipW / 2, y: m.t + 23.5, "text-anchor": "middle" },
          "median-chip-text", label));
      }
      if (spec.id === "activity") {
        // region tags, mono uppercase (the reference's HUMAN / AI corner tags)
        g.appendChild(svgEl("text",
          { x: m.l + 14, y: m.t + 24 }, "quad-tag", "FEW COMMITS, HIGH IMPACT"));
        g.appendChild(svgEl("text",
          { x: W - m.r - 14, y: PY(1) - 18, "text-anchor": "end" }, "quad-tag",
          "MANY COMMITS, MID-BOARD"));
      }
      svg.appendChild(g);
    });

    // --- dots: one <g> per author (dot + focus stop), moved only via
    // transform on the group. Radius and ramp fill encode rank percentile.
    // All dots live in one .dot-layer group: above the axis layers, below
    // the callout overlays.
    var points = [];
    var dotLayer = svgEl("g", {}, "dot-layer");
    AUTHORS.forEach(function (a, ai) {
      var start = a.views.spectrum;
      var pct = impactPct(a);
      var r = dotRadius(pct);
      var g = svgEl("g", {}, "pt");
      var dot = svgEl("circle", { r: r.toFixed(1), cx: 0, cy: 0,
        fill: rampColor(pct) }, "dot");
      var hit = svgEl("circle", // roving tabindex: only rank 1 is a tab stop
        { r: 10, cx: 0, cy: 0, tabindex: ai === 0 ? 0 : -1, role: "button" }, "dot-hit");
      hit.setAttribute("aria-label",
        a.name + " — impact " + a.impact.toFixed(3) + ", " +
        plural(a.commits, "commit") + ", rank " + a.rank + ", tier " + a.tier);
      g.appendChild(dot); g.appendChild(hit);
      var p = { a: a, g: g, dot: dot, hit: hit, r: r, dim: false,
                cx: PX(start[0]), cy: PY(0.5),
                // spring state: velocity, target, settled flag, and a small
                // deterministic per-dot stiffness jitter so the field
                // settles organically instead of in lockstep
                vx: 0, vy: 0, tx: PX(start[0]), ty: PY(0.5), settled: true,
                k: 90 * (0.9 + 0.2 * (((ai * 2654435761) % 997) / 997)),
                wakeAt: 0,
                fs: 1, fox: 0, foy: 0 }; // loupe scale + offset (eased)
      function place(x, y, suffix) {
        p.cx = x; p.cy = y;
        g.setAttribute("transform",
          "translate(" + x.toFixed(1) + " " + y.toFixed(1) + ")" + (suffix || ""));
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
      dotLayer.appendChild(g);
      points.push(p);
    });
    svg.appendChild(dotLayer);

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

    // --- spectrum callouts: numbered marks, no leader lines. Each top dot
    // carries its rank numeral (below it when a stacked tie sits above);
    // a corner key maps numerals to names. Precise with zero spaghetti.
    var specOverlay = svgEl("g", {}, "axis-layer");
    specOverlay.dataset.view = "spectrum";
    (function spectrumCallouts() {
      var top = AUTHORS.slice(0, Math.min(6, AUTHORS.length));
      if (!top.length) return;
      var placed = [];
      top.forEach(function (a) {
        var cx = PX(a.views.spectrum[0]);
        var cy = PY(a.views.spectrum[1]);
        var r = dotRadius(impactPct(a));
        // exact-tie stack (same x): later ranks label below the whole stack
        var stack = placed.filter(function (q) { return Math.abs(q.cx - cx) < 8; });
        var ny;
        if (stack.length) {
          ny = Math.max.apply(null, stack.map(function (q) {
            return Math.max(q.cy + q.r, q.ny);
          })) + 13;
        } else {
          ny = cy - r - 6;
        }
        placed.push({ cx: cx, cy: Math.max(cy, ny - 4), r: r, ny: ny });
        specOverlay.appendChild(svgEl("text",
          { x: cx, y: ny, "text-anchor": "middle" }, "callout-rank",
          String(a.rank)));
      });
      // corner key: fixed numeral column, names left-aligned beside it
      var maxNameW = Math.max.apply(null, top.map(function (a) {
        return a.name.length;
      })) * 6.6;
      var numX = W - m.r - maxNameW - 12;
      var keyY = m.t + 14;
      top.forEach(function (a, i) {
        var y = keyY + i * 16.5;
        specOverlay.appendChild(svgEl("text",
          { x: numX, y: y, "text-anchor": "end" }, "callout-rank",
          String(a.rank)));
        specOverlay.appendChild(svgEl("text",
          { x: numX + 8, y: y }, "callout-name", a.name));
      });
    })();
    svg.appendChild(specOverlay);

    // --- tiers annotation: name the tall column instead of leaving it mute
    var tiersOverlay = svgEl("g", {}, "axis-layer axis-hidden");
    tiersOverlay.dataset.view = "tiers";
    (function tiersAnnotation() {
      var biggest = D.tiers.reduce(function (m2, t) {
        return t.count > m2.count ? t : m2;
      }, D.tiers[0]);
      if (!biggest || biggest.count < 8) return;
      var members = AUTHORS.filter(function (a) { return a.tier === biggest.tier; });
      var cx = PX(members[0].views.tiers[0]);
      var topY = Math.min.apply(null, members.map(function (a) {
        return PY(a.views.tiers[1]);
      }));
      var lx = Math.min(cx, W - m.r - 150);
      tiersOverlay.appendChild(svgEl("text",
        { x: lx, y: topY - 14, "text-anchor": "middle" }, "callout-note",
        biggest.count + " contributors, one tier"));
      tiersOverlay.appendChild(svgEl("line",
        { x1: lx, y1: topY - 10, x2: cx, y2: topY - 5 }, "leader"));
    })();
    svg.appendChild(tiersOverlay);
    document.getElementById("field-svg").appendChild(svg);

    // SIGNALS is in [ownership, survival, coupling, review] order
    var VIEW_SIGNAL = {
      own: SIGNALS[0], surv: SIGNALS[1], coup: SIGNALS[2], rev: SIGNALS[3]
    };
    function showPointTip(a, x, y) {
      var line2 = plural(a.commits, "commit") + " · rank " + a.rank + " · tier " + a.tier;
      if (state.view === "signals") {
        var s = VIEW_SIGNAL[state.signal];
        line2 = s.label + " " + pctLabel(a.signals[s.key]) + " · " + line2;
      }
      tipShow([{ v: a.impact.toFixed(3), l: a.name }, { l: line2 }], x, y);
    }

    // --- spring physics: one rAF, per-dot critically-damped springs.
    // Retargeting only rewrites (tx,ty), so momentum survives view switches
    // and every morph is interruptible. During flight each dot elongates
    // along its motion vector (velocity-stretch) and snaps crisp at rest.
    // The loop sleeps when every dot rests, so idle CPU stays at zero.
    // stagger=true (opening bloom only) delays each dot's wake by rank.
    var anim = null, lastT = 0;
    // loupe focus (viewBox coords): dots near the pointer swell and separate
    // with a gaussian falloff — a magnifier over the instrument, eased so it
    // breathes instead of snapping. Hit-testing stays on the true (cx,cy).
    var fx = 0, fy = 0, fActive = false;
    var SIG2 = 2 * 55 * 55;
    function springFrame(now) {
      var dt = Math.min((now - lastT) / 1000, 1 / 30);
      lastT = now;
      var alive = false;
      points.forEach(function (p) {
        if (gravityMode) { alive = gravityStep(p, dt) || alive; return; }
        var suffix = "";
        if (!p.settled) {
          if (now < p.wakeAt) {
            alive = true;
          } else {
            var c = 2 * Math.sqrt(p.k); // critical damping
            p.vx += (p.k * (p.tx - p.cx) - c * p.vx) * dt;
            p.vy += (p.k * (p.ty - p.cy) - c * p.vy) * dt;
            var nx = p.cx + p.vx * dt, ny = p.cy + p.vy * dt;
            var speed = Math.sqrt(p.vx * p.vx + p.vy * p.vy);
            if (Math.abs(p.tx - nx) < 0.1 && Math.abs(p.ty - ny) < 0.1 && speed < 8) {
              p.vx = 0; p.vy = 0; p.cx = p.tx; p.cy = p.ty; p.settled = true;
            } else {
              alive = true;
              p.cx = nx; p.cy = ny;
              var s = Math.min(1 + speed * 0.0005, 1.6); // oscilloscope stretch
              if (s > 1.02) {
                var deg = Math.atan2(p.vy, p.vx) * 180 / Math.PI;
                suffix = " rotate(" + deg.toFixed(1) + ") scale(" + s.toFixed(3) +
                  " " + (1 / Math.sqrt(s)).toFixed(3) + ") rotate(" +
                  (-deg).toFixed(1) + ")";
              }
            }
          }
        }
        var ts = 1, tox = 0, toy = 0;
        if (fActive) {
          var dx = p.cx - fx, dy = p.cy - fy, d2 = dx * dx + dy * dy;
          var gau = Math.exp(-d2 / SIG2);
          if (gau > 0.02) {
            ts = 1 + 0.5 * gau;
            var dist = Math.sqrt(d2) || 1;
            tox = dx / dist * 11 * gau; toy = dy / dist * 11 * gau;
          }
        }
        p.fs += (ts - p.fs) * 0.22;
        p.fox += (tox - p.fox) * 0.22;
        p.foy += (toy - p.foy) * 0.22;
        var hasF = Math.abs(p.fs - 1) > 0.004 ||
                   Math.abs(p.fox) > 0.05 || Math.abs(p.foy) > 0.05;
        if (hasF) alive = true;
        else if (p.fs !== 1) { p.fs = 1; p.fox = 0; p.foy = 0; }
        if (!suffix && p.fs > 1.004) suffix = " scale(" + p.fs.toFixed(3) + ")";
        p.g.setAttribute("transform",
          "translate(" + (p.cx + p.fox).toFixed(1) + " " +
          (p.cy + p.foy).toFixed(1) + ")" + suffix);
      });
      anim = alive ? requestAnimationFrame(springFrame) : null;
    }
    function wake() {
      if (!anim) { lastT = performance.now(); anim = requestAnimationFrame(springFrame); }
    }
    function retarget(stagger) {
      gravityMode = false; // any re-aim (view switch, mixer, restore) ends gravity
      var spec = VIEWS.filter(function (v) { return v.id === state.view; })[0];
      // shipped annotations (median chip, rank callouts) are stale over a
      // custom-weight distribution — hidden via CSS while the mix is bent
      svg.classList.toggle("mix-bent", !!mixScores);
      var now = performance.now();
      points.forEach(function (p) {
        var c = spec.coords(p.a);
        // the mixer lab bends spectrum x to the custom score (y-offset kept:
        // approximate collision is fine for a what-if lens; springs carry it)
        if (mixScores && state.view === "spectrum") c = [mixScores[p.a.name], c[1]];
        p.tx = PX(c[0]); p.ty = PY(c[1]);
        if (reducedMotion) { p.place(p.tx, p.ty); return; }
        p.settled = false;
        p.wakeAt = stagger ? now + (p.a.rank - 1) * 6 : 0;
      });
      if (!reducedMotion) wake();
    }

    // --- "gravity" easter egg: type the word and every dot falls, piles on
    // the baseline, and bounces; any view switch / Escape / a second "gravity"
    // springs the whole field back into formation (retarget clears the flag,
    // and the critically-damped springs carry the momentum home). Reuses the
    // same points + rAF; honors reduced-motion by no-op.
    var gravityMode = false;
    var GRAV = 2000; // px/s^2 downward
    function gravityStep(p, dt) {
      p.vy += GRAV * dt;
      p.cx += p.vx * dt;
      p.cy += p.vy * dt;
      var floor = PY(1) - p.r;
      if (p.cy >= floor) {
        p.cy = floor;
        if (p.vy > 55) p.vy = -p.vy * 0.5; // bounce while it still has energy
        else p.vy = 0;                     // otherwise settle onto the baseline
        p.vx *= 0.8;
        if (Math.abs(p.vx) < 3) p.vx = 0;
      }
      var lw = m.l + p.r, rw = W - m.r - p.r;
      if (p.cx < lw) { p.cx = lw; p.vx = Math.abs(p.vx) * 0.55; }
      else if (p.cx > rw) { p.cx = rw; p.vx = -Math.abs(p.vx) * 0.55; }
      p.g.setAttribute("transform",
        "translate(" + p.cx.toFixed(1) + " " + p.cy.toFixed(1) + ")");
      return p.vx !== 0 || p.vy !== 0 || p.cy < floor - 0.5;
    }
    function toggleGravity() {
      if (reducedMotion) return;             // the egg is pure motion; honor the setting
      if (gravityMode) { retarget(); return; } // second trigger: spring back home
      gravityMode = true;
      fActive = false;                        // drop the loupe
      crossG.setAttribute("display", "none"); // and the crosshair
      var box = svg.getBoundingClientRect();  // pull the field into view if it's off-screen
      if (box.bottom < 40 || box.top > window.innerHeight - 40) {
        document.getElementById("field").scrollIntoView({ behavior: "smooth", block: "center" });
      }
      points.forEach(function (p) {
        p.settled = false;
        p.vx = (Math.random() - 0.5) * 300;   // scatter sideways
        p.vy = -Math.random() * 80;           // with a small upward pop
        p.wakeAt = 0;
      });
      wake();
    }
    toggleGravity.isOn = function () { return gravityMode; };
    toggleGravity.off = function () { if (gravityMode) retarget(); };
    fieldGravity = toggleGravity;

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
    // --- instrument crosshair: hairline reticle + mono readout, mouse only
    var crossG = svgEl("g", { display: "none" }, "crosshair");
    var chV = svgEl("line", { y1: m.t, y2: PY(1) });
    var chH = svgEl("line", { x1: m.l, x2: W - m.r });
    var chTxt = svgEl("text", {}, "crosshair-txt");
    crossG.appendChild(chV); crossG.appendChild(chH); crossG.appendChild(chTxt);
    svg.insertBefore(crossG, dotLayer); // under the dots, over the grid
    function crosshair(sx, sy) {
      if (sx < m.l || sx > W - m.r || sy < m.t || sy > PY(1)) {
        crossG.setAttribute("display", "none"); return;
      }
      crossG.removeAttribute("display");
      chV.setAttribute("x1", sx); chV.setAttribute("x2", sx);
      chH.setAttribute("y1", sy); chH.setAttribute("y2", sy);
      var fr = (sx - m.l) / pw, label = "";
      if (state.view === "spectrum") label = "impact " + fr.toFixed(3);
      else if (state.view === "signals") label = ordinal(Math.round(fr * 100)) + " pct";
      // activity carries impact on y (ny = 1 - impact in the precomputed layout)
      else if (state.view === "activity") label = "impact " + (1 - (sy - m.t) / ph).toFixed(3);
      chTxt.textContent = label;
      if (label) {
        var flip = sx > m.l + pw * 0.8;
        chTxt.setAttribute("x", sx + (flip ? -8 : 8));
        chTxt.setAttribute("y", m.t + 16);
        chTxt.setAttribute("text-anchor", flip ? "end" : "start");
      }
    }
    svg.addEventListener("pointermove", function (ev) {
      var box = svg.getBoundingClientRect();
      var sx = (ev.clientX - box.left) * W / box.width;
      var sy = (ev.clientY - box.top) * H / box.height;
      if (ev.pointerType !== "touch") {
        crosshair(sx, sy);
        if (!reducedMotion) { fx = sx; fy = sy; fActive = true; wake(); }
      }
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
      crossG.setAttribute("display", "none");
      if (fActive) { fActive = false; wake(); } // ease the loupe back out
    });
    // continuity (dot -> row): a proxy dot flies to where the row will land
    function flyToBoard(p) {
      if (reducedMotion || !document.body.animate) return;
      var box = svg.getBoundingClientRect();
      var x0 = box.left + p.cx * box.width / W;
      var y0 = box.top + p.cy * box.height / H;
      var d = document.createElement("div");
      d.className = "proxy-dot";
      d.style.background = p.dot.getAttribute("fill");
      d.style.left = x0 + "px"; d.style.top = y0 + "px";
      document.body.appendChild(d);
      // fly to viewport center: the row is scrolled to block:center, so this
      // is its known destination (never chase the moving rect)
      var dx = window.innerWidth / 2 - x0, dy = window.innerHeight / 2 - y0;
      d.animate([
        { transform: "translate(0,0) scale(1)", opacity: 1 },
        { transform: "translate(" + dx + "px," + dy + "px) scale(1.5)",
          opacity: 0.9, offset: 0.8 },
        { transform: "translate(" + dx + "px," + dy + "px) scale(0.3)", opacity: 0 }
      ], { duration: 650, easing: "cubic-bezier(0.16, 1, 0.3, 1)" })
        .onfinish = function () { d.remove(); };
    }
    svg.addEventListener("click", function (ev) {
      var p = nearestPoint(ev);
      if (lastPointerType === "touch") {
        // touch: pin the strip below the chart (hover never happens here)
        if (p) pinContributor(p);
        else if (pinStrip) pinStrip.hidden = true;
        return;
      }
      if (p) { flyToBoard(p); jumpToAuthor(p.a.name); }
    });
    // continuity (row -> dot): the leaderboard detail lights this author's dot
    highlightDot = function (name) {
      var p = null;
      points.forEach(function (q) { if (q.a.name === name) p = q; });
      if (!p) return;
      var r = svg.getBoundingClientRect();
      if (r.bottom < 0 || r.top > window.innerHeight) return;
      p.dot.classList.add("hot");
      setTimeout(function () {
        if (p !== hotPoint) p.dot.classList.remove("hot");
      }, 1400);
    };

    // --- controls: view radiogroup, signal radiogroup, filter chips
    function radiogroup(host, items, isChecked, onPick) {
      var buttons = items.map(function (it) {
        var b = el("button");
        if (it.short) { // long label on desktop, short on phones
          b.appendChild(el("span", "lbl-l", it.label));
          b.appendChild(el("span", "lbl-s", it.short));
        } else {
          b.textContent = it.label;
        }
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
    // captions crossfade between views (the field morphs smoothly under them,
    // so a hidden-attribute snap clashed). The template's hidden attributes
    // only serve the no-JS render; JS strips them and drives a class instead.
    var caps = document.querySelectorAll(".field-caption p");
    function syncCaps(id) {
      caps.forEach(function (cap) {
        cap.hidden = false;
        cap.classList.toggle("cap-on", cap.dataset.view === id);
      });
    }
    syncCaps(state.view);
    function setView(id) {
      state.view = id;
      if (typeof onFieldViewChange === "function") onFieldViewChange(id);
      syncViews();
      signalHost.hidden = id !== "signals";
      svg.querySelectorAll(".axis-layer").forEach(function (g) {
        g.classList.toggle("axis-hidden", g.dataset.view !== id);
      });
      syncCaps(id);
      retarget();
      positionThumbs();
    }
    var syncViews = radiogroup(
      document.getElementById("field-views"), VIEWS,
      function (id) { return id === state.view; },
      setView);

    var SIGNAL_VIEWS = [
      { id: "own", label: "Ownership" }, { id: "surv", label: "Survival" },
      { id: "coup", label: "Coupling" }, { id: "rev", label: "Reviews" }
    ];
    var syncSignals = radiogroup(signalHost, SIGNAL_VIEWS,
      function (id) { return id === state.signal; },
      function (id) { state.signal = id; syncSignals(); retarget(); positionThumbs(); });

    // sliding thumbs under the checked tab (both radiogroups)
    var thumbFns = [];
    function makeThumb(host) {
      var t = el("div", "seg-thumb");
      host.insertBefore(t, host.firstChild);
      thumbFns.push(function () {
        var b = host.querySelector('[aria-checked="true"]');
        if (!b || host.hidden) { t.style.opacity = "0"; return; }
        t.style.opacity = "1";
        t.style.width = b.offsetWidth + "px";
        t.style.transform = "translateX(" + b.offsetLeft + "px)";
      });
    }
    function positionThumbs() { thumbFns.forEach(function (f) { f(); }); }
    makeThumb(document.getElementById("field-views"));
    makeThumb(signalHost);
    window.addEventListener("resize", positionThumbs);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(positionThumbs);
    positionThumbs();

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
      if (c.count === 0) return; // a filter that matches nobody is dead UI
      var b = el("button", "chip-toggle");
      b.type = "button";
      b.setAttribute("aria-pressed", "false");
      if (c.glyph) {
        var gl = el("span", "warn-glyph", c.glyph + " ");
        if (c.glyph === "◌") gl.classList.add("glyph-low"); // ◌ renders high of optical center
        b.appendChild(gl);
      }
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
        p.g.classList.toggle("dim", p.dim);
        if (match) n += 1;
      });
      countEl.textContent = active.length ? n + " / " + AUTHORS.length : "";
    }
    applyFilters();

    /* ------------------------- the story: steps drive the same setView the
       tabs use, so the two affordances can never disagree */
    (function story() {
      var stepEls = document.querySelectorAll(".story-rail .step");
      var progress = document.querySelectorAll("#story-progress i");
      var noteEl = document.getElementById("explore-note");
      if (!stepEls.length || !("IntersectionObserver" in window)) return;
      var ORDER = ["spectrum", "activity", "signals", "tiers"];
      var SIGNAL_SEQ = ["own", "surv", "coup", "rev"];
      var autoTimer = null;
      var signalsTouched = false;
      var signalsPlayed = false;
      // any manual signal pick cancels the auto-advance for good
      signalHost.addEventListener("pointerdown", function () {
        signalsTouched = true;
        if (autoTimer) { clearInterval(autoTimer); autoTimer = null; }
      });
      function autoCycleSignals() {
        if (signalsTouched || signalsPlayed || reducedMotion) return;
        signalsPlayed = true; // runs once per visit, never re-arms
        var i = 0;
        autoTimer = setInterval(function () {
          i += 1;
          if (i >= SIGNAL_SEQ.length || signalsTouched || state.view !== "signals") {
            clearInterval(autoTimer); autoTimer = null;
            return;
          }
          state.signal = SIGNAL_SEQ[i];
          syncSignals();
          retarget();
          positionThumbs();
        }, 1600);
      }
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) {
          if (!e.isIntersecting) return;
          var id = e.target.dataset.step;
          stepEls.forEach(function (s) {
            s.classList.toggle("active", s === e.target);
          });
          var idx = ORDER.indexOf(id);
          progress.forEach(function (p, i) {
            p.classList.toggle("on", i <= idx);
          });
          if (state.view !== id) setView(id);
          if (id === "signals") autoCycleSignals();
          if (id === "tiers" && noteEl) noteEl.hidden = false;
        });
      }, { rootMargin: "-42% 0px -42% 0px", threshold: 0 });
      stepEls.forEach(function (s) { io.observe(s); });
    })();

    // --- roving arrow-key navigation through the dots (one tab stop total)
    (function rovingDots() {
      var current = 0;
      function focusDot(i) {
        i = Math.max(0, Math.min(points.length - 1, i));
        points[current].hit.setAttribute("tabindex", "-1");
        current = i;
        points[current].hit.setAttribute("tabindex", "0");
        points[current].hit.focus();
      }
      dotLayer.addEventListener("keydown", function (ev) {
        var step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[ev.key];
        if (ev.key === "Home") { ev.preventDefault(); focusDot(0); return; }
        if (ev.key === "End") { ev.preventDefault(); focusDot(points.length - 1); return; }
        if (!step) return;
        ev.preventDefault();
        focusDot(current + step);
      });
      dotLayer.setAttribute("role", "group");
      dotLayer.setAttribute("aria-label",
        "Contributor dots, ordered by rank. Use arrow keys to move between contributors.");
    })();

    // --- tap-to-pin: the touch answer to hover (fixed strip under the chart)
    var pinStrip = null;
    function pinContributor(p) {
      if (!pinStrip) {
        pinStrip = el("div", "pin-strip");
        var stage = document.querySelector(".field-stage");
        stage.parentNode.insertBefore(pinStrip, stage.nextSibling);
      }
      pinStrip.hidden = false;
      pinStrip.textContent = "";
      var dot = el("span", "pin-dot");
      dot.style.background = p.dot.getAttribute("fill");
      pinStrip.appendChild(dot);
      // name over meta in one shrinkable column so long names ellipsize
      // instead of wrapping the whole strip (390px audit finding)
      var label = el("span", "pin-txt");
      label.appendChild(el("b", null, p.a.name));
      label.appendChild(el("span", "pin-meta",
        "T" + p.a.tier + " · " + p.a.impact.toFixed(3) + " · rank " + p.a.rank));
      pinStrip.appendChild(label);
      var go = el("button", null, "view in table →");
      go.type = "button";
      go.addEventListener("click", function () { jumpToAuthor(p.a.name); });
      pinStrip.appendChild(go);
      if (hashSetC) hashSetC(p.a.name);
    }
    var lastPointerType = "mouse";
    svg.addEventListener("pointerdown", function (ev) {
      lastPointerType = ev.pointerType || "mouse";
    }, { passive: true });

    // --- scrollBus: one passive listener + one rAF for the new scroll
    // consumers (dot inertia + story gauge). The four shipped handlers
    // elsewhere keep their own ticking pattern.
    (function scrollBus() {
      if (reducedMotion) return;
      var storyGrid = document.querySelector(".story-grid");
      var dashes = document.querySelectorAll("#story-progress i");
      var lastY = window.scrollY, ticking = false;
      function tick() {
        ticking = false;
        var y = window.scrollY;
        var dy = y - lastY;
        lastY = y;
        // inertia: the instrument has mass — dots trail the scroll and
        // spring back. Accumulated-velocity clamp (trackpads stack events);
        // teleport guard so anchor jumps don't detonate the field.
        if (dy !== 0 && Math.abs(dy) <= 120) {
          var r = svg.getBoundingClientRect();
          if (r.bottom > 0 && r.top < window.innerHeight) {
            points.forEach(function (p) {
              p.vy = Math.max(-70, Math.min(70, p.vy + dy * 0.5));
              p.settled = false;
            });
            wake();
          }
        }
        // gauge: dashes fill continuously with progress through the story
        if (storyGrid && dashes.length) {
          var sr = storyGrid.getBoundingClientRect();
          if (sr.bottom > 0 && sr.top < window.innerHeight) {
            var prog = (window.innerHeight * 0.58 - sr.top) / sr.height;
            prog = Math.max(0, Math.min(1, prog));
            dashes.forEach(function (d, i) {
              var f = Math.max(0, Math.min(1, prog * dashes.length - i));
              d.style.setProperty("--fill", f.toFixed(3));
            });
          }
        }
      }
      window.addEventListener("scroll", function () {
        if (!ticking) { ticking = true; requestAnimationFrame(tick); }
      }, { passive: true });
    })();

    setFieldView = setView; // hash-state routing drives the same code path
    fieldRetarget = retarget; // the mixer lab re-aims the spectrum through here

    // opening bloom: dots start on the axis line and swarm into place —
    // deferred to the card's first entry into the viewport so the swarm is
    // actually witnessed (it used to fire on load with the card ~1900px below
    // the fold and settle unseen). Story-driver safe: its IO only calls
    // setView when the view changes, and step 01 is already "spectrum".
    (function bloom() {
      if (reducedMotion || !("IntersectionObserver" in window)) {
        retarget(true); // places instantly under reduced motion
        return;
      }
      var bloomed = false;
      function fire(instant) {
        if (bloomed) return;
        bloomed = true;
        io.disconnect();
        retarget(true);
        if (instant) { // settle in place, no flight
          points.forEach(function (p) {
            p.vx = 0; p.vy = 0; p.settled = true; p.place(p.tx, p.ty);
          });
        }
      }
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) { if (e.isIntersecting) fire(false); });
      }, { threshold: 0.25 });
      io.observe(document.getElementById("field"));
      // print guard: never print the parked mid-axis line
      window.addEventListener("beforeprint", function () { fire(true); });
    })();
  })();

  /* ----------------------------------------------------------- leaderboard */
  var body = document.getElementById("board-body");
  var search = document.getElementById("search");
  var rowCount = document.getElementById("row-count");
  var boardFoot = document.getElementById("board-foot");
  var state = { key: "rank", dir: 1, query: "", showAll: false };
  var openName = null;
  var DISCLOSE_TIERS = 15; // default view: tiers 1..15, then "Show all"
  var updateSeg = function () {}; // bound by thesisToggle below
  var writeHash = function () {}; // bound by hashState below
  var currentFieldView = "spectrum"; // mirrored from the field via onFieldViewChange

  // bar growth on first viewport entry: one-shot per AUTHOR (never re-animates
  // across sorts/searches — frequency law), rows themselves never hide
  var seenRows = {};
  var rowIO = (!reducedMotion && "IntersectionObserver" in window)
    ? new IntersectionObserver(function (entries) {
        var batch = 0;
        entries.forEach(function (e) {
          if (!e.isIntersecting) return;
          var fill = e.target.querySelector(".cbar .fill");
          if (fill) fill.style.transitionDelay = Math.min(batch * 20, 60) + "ms";
          batch += 1;
          e.target.classList.add("seen");
          seenRows[e.target.dataset.name] = true;
          rowIO.unobserve(e.target);
        });
      }, { threshold: 0.1 })
    : null;

  function monogramText(name) {
    // unicode-safe initials: first grapheme of the first two words
    var clean = name.replace(/<[^>]*>/g, "").trim();
    var words = clean.split(/\s+/).filter(Boolean).slice(0, 2);
    function first(s) {
      if (window.Intl && Intl.Segmenter) {
        var it = new Intl.Segmenter(undefined, { granularity: "grapheme" })
          .segment(s)[Symbol.iterator]().next();
        return it.done ? "" : it.value.segment;
      }
      return s.charAt(0);
    }
    var initials = words.map(first).join("");
    return initials ? initials.toUpperCase() : "?";
  }

  function accessor(key) {
    if (key === "rank") return function (a) { return a.rank; };
    if (key === "name") return function (a) { return a.name.toLowerCase(); };
    if (key === "impact") return function (a) { return a.impact; };
    if (key === "commits") return function (a) { return a.commits; };
    // custom-weight scores from the mixer lab (rank fallback guards a
    // hand-edited #sort=mix URL arriving before any slider has moved)
    if (key === "mix") return function (a) { return mixLab ? mixLab.score[a.name] : -a.rank; };
    return function (a) { return a.signals[key]; };
  }

  function visibleAuthors() {
    var q = state.query.trim().toLowerCase();
    var list = AUTHORS.filter(function (a) {
      return !q || a.name.toLowerCase().indexOf(q) !== -1;
    });
    var get = accessor(state.key);
    list = list.slice().sort(function (a, b) {
      if (q) { // starts-with matches rank first while filtering
        var sa = a.name.toLowerCase().indexOf(q) === 0 ? 0 : 1;
        var sb = b.name.toLowerCase().indexOf(q) === 0 ? 0 : 1;
        if (sa !== sb) return sa - sb;
      }
      var va = get(a), vb = get(b);
      var c = va < vb ? -1 : va > vb ? 1 : a.rank - b.rank;
      return c * state.dir;
    });
    return list;
  }

  function microBar(pct, imputed, wide, sigKey) {
    var wrap = el("div", wide ? "cbar" : "sig-wrap");
    var track = el("div", "track");
    var fill = el("div", "fill" + (imputed ? " imputed" : ""));
    if (wide) {
      // ramp bar: full-track gradient, width revealed via clip-path (--w)
      fill.style.setProperty("--w", (pct * 100).toFixed(1) + "%");
    } else {
      fill.style.width = (pct * 100).toFixed(1) + "%";
      if (sigKey) {
        fill.style.setProperty("--sig-color", SIG_COLORS[sigKey]);
        if (!imputed) fill.style.background = SIG_COLORS[sigKey];
      }
    }
    track.appendChild(fill);
    wrap.appendChild(track);
    if (wide) wrap.appendChild(el("span", "val", pct.toFixed(3)));
    return wrap;
  }

  function buildRow(a) {
    var tr = el("tr", "row");
    tr.dataset.name = a.name;

    if (seenRows[a.name] || !rowIO) tr.classList.add("seen");
    // under custom weights the rank and score cells show the lab's numbers;
    // tier chips, badges, and details stay on the shipped scoring
    var mixOn = state.key === "mix" && mixLab;
    var rank = el("td", "num", String(mixOn ? mixLab.rank[a.name] : a.rank));
    var name = el("td", "name-cell");
    name.appendChild(el("span",
      "monogram" + (a.tier === 1 ? " t1" : ""), monogramText(a.name)));
    // the disclosure control is a real button (aria-expanded is invalid on a
    // plain-table row); its click bubbles to the row's toggle handler
    var btn = el("button", "row-btn");
    btn.type = "button";
    btn.setAttribute("aria-expanded", "false");
    // search-match highlighting: substring wrapped in <mark>; the name enters
    // the DOM via text nodes only (never markup)
    var q = state.query.trim().toLowerCase();
    var at = q ? a.name.toLowerCase().indexOf(q) : -1;
    if (at >= 0) {
      btn.appendChild(document.createTextNode(a.name.slice(0, at)));
      btn.appendChild(el("mark", null, a.name.slice(at, at + q.length)));
      btn.appendChild(document.createTextNode(a.name.slice(at + q.length)));
    } else {
      btn.appendChild(document.createTextNode(a.name));
    }
    btn.addEventListener("keydown", function (ev) {
      if (ev.key !== "ArrowDown" && ev.key !== "ArrowUp") return;
      ev.preventDefault();
      var btns = Array.prototype.slice.call(body.querySelectorAll(".row-btn"));
      var i = btns.indexOf(btn) + (ev.key === "ArrowDown" ? 1 : -1);
      if (btns[i]) btns[i].focus();
    });
    name.appendChild(btn);
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
    impact.appendChild(microBar(mixOn ? mixLab.score[a.name] : a.impact, false, true));
    tr.appendChild(rank); tr.appendChild(name); tr.appendChild(impact);

    SIGNALS.forEach(function (s) {
      var td = el("td", "sig");
      td.appendChild(microBar(a.signals[s.key],
        s.key === "review_leverage" && a.flags.review_imputed, false, s.key));
      tr.appendChild(td);
    });

    var flags = el("td", "w-flags");
    if (a.flags.bus_factor) {
      // the flag is an entry point, not decoration: it opens the departure
      // simulator preselected on this author (stopPropagation like ↗ and ⇄)
      var bf = el("button", "badge badge-warn badge-link", "⚠ bus-factor");
      bf.type = "button";
      bf.setAttribute("aria-label",
        "Departure risk for " + a.name + " — see the team view");
      bf.addEventListener("click", function (ev) {
        ev.stopPropagation();
        if (orgSimSet) orgSimSet(a.name);
      });
      flags.appendChild(bf);
    }
    if (a.flags.review_imputed) {
      if (flags.firstChild) flags.appendChild(document.createTextNode(" "));
      flags.appendChild(el("span", "badge badge-mut", "◌ no review data"));
    }
    // compare affordance: hover/focus-revealed ⇄; stopPropagation like the ↗
    // link so it never toggles the row's detail
    if (compareToggle) {
      var on = compareHas && compareHas(a.name);
      var cmp = el("button", "row-compare", "⇄");
      cmp.type = "button";
      cmp.dataset.name = a.name;
      cmp.setAttribute("aria-label", (on ? "Remove " : "Add ") + a.name +
        (on ? " from" : " to") + " comparison");
      cmp.setAttribute("aria-pressed", on ? "true" : "false");
      if (on) tr.classList.add("comparing");
      cmp.addEventListener("click", function (ev) {
        ev.stopPropagation();
        compareToggle(a.name);
      });
      flags.appendChild(cmp);
    }
    tr.appendChild(flags);

    // one toggle path: pointer clicks anywhere on the row and the button's
    // native Enter/Space both land here by bubbling
    tr.addEventListener("click", function () { toggleDetail(tr, a); });
    return tr;
  }

  function render() {
    body.textContent = "";
    boardFoot.textContent = "";
    openName = null;
    var list = visibleAuthors();
    var defaultOrder = state.key === "rank" && state.dir === 1 && !state.query.trim();
    // progressive disclosure applies only to the untouched default view;
    // any search or sort works on the full set
    var shown = list;
    if (defaultOrder && !state.showAll) {
      shown = list.filter(function (a) { return a.tier <= DISCLOSE_TIERS; });
      if (shown.length === list.length) state.showAll = true;
    }
    var lastTier = null;
    shown.forEach(function (a) {
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
    if (defaultOrder && !state.showAll && shown.length < list.length) {
      var more = el("button", "pill-ink",
        "Show all " + AUTHORS.length + " contributors");
      more.type = "button";
      more.addEventListener("click", function () {
        state.showAll = true;
        render();
      });
      boardFoot.appendChild(more);
    }
    if (!list.length) {
      var empty = el("div", "empty-state");
      var face = el("div", "empty-face");
      face.appendChild(el("i")); face.appendChild(el("i")); face.appendChild(el("i"));
      empty.appendChild(face);
      empty.appendChild(document.createTextNode(
        "No one matches “" + state.query.trim() + "”. Try a shorter name, or"));
      var clear = el("button", null, "clear the filter");
      clear.type = "button";
      clear.addEventListener("click", function () {
        search.value = ""; state.query = ""; render(); search.focus();
      });
      empty.appendChild(clear);
      empty.appendChild(document.createTextNode("."));
      boardFoot.appendChild(empty);
    }
    rowCount.textContent = (defaultOrder && !state.showAll ? shown.length : list.length) +
      " / " + AUTHORS.length;
    document.querySelectorAll(".board thead th[data-sort]").forEach(function (th) {
      if (th.dataset.sort === state.key) {
        th.setAttribute("aria-sort", state.dir === 1 ? "ascending" : "descending");
      } else {
        th.removeAttribute("aria-sort");
      }
    });
    updateSeg();
    if (rowIO) {
      body.querySelectorAll("tr.row:not(.seen)").forEach(function (r) {
        rowIO.observe(r);
      });
    }
  }

  /* FLIP reorder: rows fly to their new positions on sort (never on search
     keystrokes — high-frequency interactions stay instant). Rows are matched
     by dataset.name because render() rebuilds every node. */
  function flipRender() {
    var before = {};
    if (!reducedMotion) {
      body.querySelectorAll("tr.row").forEach(function (r) {
        before[r.dataset.name] = r.getBoundingClientRect().top;
      });
    }
    render();
    if (reducedMotion) return;
    var movers = [];
    body.querySelectorAll("tr.row").forEach(function (r) {
      if (movers.length >= 30) return;
      var old = before[r.dataset.name];
      if (old === undefined) return;
      var d = old - r.getBoundingClientRect().top;
      if (!d || Math.abs(d) > window.innerHeight) return;
      r.style.transition = "none";
      r.style.transform = "translateY(" + d.toFixed(0) + "px)";
      movers.push(r);
    });
    if (!movers.length) return;
    requestAnimationFrame(function () { requestAnimationFrame(function () {
      movers.forEach(function (r, i) {
        r.style.transition = "transform 240ms cubic-bezier(0.16, 1, 0.3, 1) " +
          Math.min(i * 8, 64) + "ms";
        r.style.transform = "";
      });
      setTimeout(function () {
        movers.forEach(function (r) { r.style.transition = ""; });
      }, 420);
    }); });
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
      flipRender();
      writeHash(false); // refinement: replaceState
    });
  });

  // tier-1 ring pulse fires once per visit: render() rebuilds rows, and a
  // recreated monogram would restart the CSS animation without this latch
  document.addEventListener("animationend", function (e) {
    if (e.animationName !== "t1-pulse") return;
    var card = document.querySelector(".board-card");
    // rAF so the sibling ring's simultaneous animationend lands first
    if (card) requestAnimationFrame(function () { card.classList.add("pulsed"); });
  });

  /* the thesis toggle (State of JS steal): flip between impact rank and raw
     commit count and watch specific people physically trade places — the
     rejected baseline made felt. */
  (function thesisToggle() {
    var tools = document.querySelector(".table-tools");
    if (!tools) return;
    var seg = el("div", "seg seg-board");
    seg.setAttribute("role", "radiogroup");
    seg.setAttribute("aria-label", "Rank the board by");
    var thumb = el("span", "seg-thumb");
    thumb.setAttribute("aria-hidden", "true");
    seg.appendChild(thumb);
    var defs = [
      { id: "impact", label: "By impact",
        on: function () { state.key = "rank"; state.dir = 1; } },
      { id: "commits", label: "By raw commits",
        on: function () { state.key = "commits"; state.dir = -1; } }
    ];
    var btns = defs.map(function (d) {
      var b = el("button", null, d.label);
      b.type = "button";
      b.setAttribute("role", "radio");
      b.addEventListener("click", function () { d.on(); flipRender(); writeHash(false); });
      seg.appendChild(b);
      return b;
    });
    tools.insertBefore(seg, tools.querySelector(".table-tools-note"));
    // the mixer's modified state must never be ambient: a visible flag sits
    // by the seg whenever custom weights own the order
    var mixFlag = el("span", "mix-flag", "◈ custom weights — set in the method lab");
    mixFlag.hidden = true;
    tools.insertBefore(mixFlag, tools.querySelector(".table-tools-note"));
    function checkedIndex() {
      if (state.key === "rank" && state.dir === 1) return 0;
      if (state.key === "commits") return 1;
      return -1; // a header sort owns the order
    }
    updateSeg = function () {
      var idx = checkedIndex();
      mixFlag.hidden = state.key !== "mix";
      btns.forEach(function (b, i) {
        b.setAttribute("aria-checked", String(i === idx));
      });
      var b = btns[idx];
      thumb.style.opacity = b ? "1" : "0";
      if (b) {
        thumb.style.width = b.offsetWidth + "px";
        thumb.style.transform = "translateX(" + b.offsetLeft + "px)";
      }
    };
    window.addEventListener("resize", updateSeg);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(updateSeg);
    updateSeg();
  })();

  /* ------------------------------------------------- weight-mixer lab
     The "equal weights are a choice, not a calibration" caveat made
     manipulable (Nicky Case): four sliders re-score all 82 as one dot
     product on the shipped percentile components. The board FLIPs into a
     custom sort mode, the spectrum bends its x, the lab lists its own top
     five. Tiers, badges, and detail panels stay on the published scoring;
     nothing here is serialized to the hash. */
  (function weightMixer() {
    var host = document.getElementById("mixer");
    if (!host || !AUTHORS.length) return;
    var rowsHost = document.getElementById("mixer-rows");
    var topHost = document.getElementById("mix-top");
    var SHORT = { ownership_concentration: "Ownership",
                  code_survival_tenure_normalized: "Survival",
                  coupling_criticality: "Coupling",
                  review_leverage: "Reviews" };
    var sliders = SIGNALS.map(function (s, i) {
      var row = el("div", "mix-row");
      var lab = el("label", "mix-lbl", SHORT[s.key] || s.label);
      lab.htmlFor = "mix-" + i;
      var input = document.createElement("input");
      input.type = "range";
      input.id = "mix-" + i;
      input.min = "0"; input.max = "100"; input.step = "1"; input.value = "25";
      input.style.accentColor = SIG_COLORS[s.key];
      var val = el("span", "mix-val", "25%");
      row.appendChild(lab); row.appendChild(input); row.appendChild(val);
      rowsHost.appendChild(row);
      return { input: input, val: val, key: s.key };
    });
    host.hidden = false;

    function weights() { // effective mix: raw values normalized to sum 1
      var raw = sliders.map(function (s) { return +s.input.value; });
      var sum = raw.reduce(function (t, v) { return t + v; }, 0);
      if (!sum) return [0.25, 0.25, 0.25, 0.25]; // all-zero = no opinion
      return raw.map(function (v) { return v / sum; });
    }
    function recompute() {
      var w = weights();
      sliders.forEach(function (s, i) {
        s.val.textContent = Math.round(w[i] * 100) + "%";
      });
      var scores = {};
      AUTHORS.forEach(function (a) {
        var t = 0;
        sliders.forEach(function (s, i) { t += w[i] * a.signals[s.key]; });
        scores[a.name] = t;
      });
      var order = AUTHORS.slice().sort(function (a, b) {
        return scores[b.name] - scores[a.name] || a.rank - b.rank;
      });
      var ranks = {};
      order.forEach(function (a, i) { ranks[a.name] = i + 1; });
      mixLab = { score: scores, rank: ranks };
      mixScores = scores;
      topHost.textContent = "";
      order.slice(0, 5).forEach(function (a) {
        var li = el("li");
        li.appendChild(el("b", null, a.name));
        li.appendChild(el("span", "mix-score",
          scores[a.name].toFixed(3) + " · shipped rank " + a.rank));
        topHost.appendChild(li);
      });
    }
    // continuous drags FLIP at most every 250ms (a re-render storm reads as
    // thrash, not motion); the trailing call always lands the exact order
    var lastFlip = 0, trailing = null;
    function requestFlip() {
      var wait = 250 - (Date.now() - lastFlip);
      if (wait <= 0) {
        lastFlip = Date.now();
        flipRender();
      } else if (!trailing) {
        trailing = setTimeout(function () {
          trailing = null;
          lastFlip = Date.now();
          flipRender();
        }, wait);
      }
    }
    function onInput() {
      recompute();
      if (state.key !== "mix") { state.key = "mix"; state.dir = -1; }
      requestFlip();
      if (fieldRetarget) fieldRetarget(); // springs are interruptible; every input may re-aim
    }
    sliders.forEach(function (s) { s.input.addEventListener("input", onInput); });
    document.getElementById("mixer-reset").addEventListener("click", function () {
      sliders.forEach(function (s) { s.input.value = "25"; s.val.textContent = "25%"; });
      topHost.textContent = "";
      mixLab = null;
      mixScores = null;
      if (trailing) { clearTimeout(trailing); trailing = null; }
      if (state.key === "mix") {
        state.key = "rank"; state.dir = 1;
        flipRender();
        writeHash(false);
      }
      if (fieldRetarget) fieldRetarget();
    });
  })();

  search.addEventListener("input", function () {
    state.query = search.value;
    render();
  });
  // combobox-lite keys: Down into the rows, Esc clears / returns
  search.addEventListener("keydown", function (ev) {
    if (ev.key === "ArrowDown") {
      var first = body.querySelector(".row-btn");
      if (first) { ev.preventDefault(); first.focus(); }
    } else if (ev.key === "Escape" && search.value) {
      ev.preventDefault();
      search.value = ""; state.query = ""; render();
    }
  });
  body.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") {
      closeDetail();
      search.focus();
    }
  });

  /* ------------------------------------------------------------- detail */
  function closeDetail() {
    var open = body.querySelector("tr.detail.open");
    if (open) {
      open.classList.remove("open");
      var row = open.previousSibling;
      var btn = row && row.querySelector && row.querySelector(".row-btn");
      if (btn) btn.setAttribute("aria-expanded", "false");
    }
    if (openName !== null) { openName = null; writeHash(false); }
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
    tr.querySelector(".row-btn").setAttribute("aria-expanded", "true");
    if (highlightDot) highlightDot(a.name); // continuity: light the field dot
    openName = a.name;
    writeHash(true); // selection is a navigation act: pushState
    detail.querySelectorAll(".dbar .fill").forEach(function (f) {
      f.style.setProperty("--w", f.dataset.w);
    });
    // sparkline draws itself on first open; the peach area fades in after
    var sw = detail.querySelector(".spark-wrap");
    if (sw && !sw.classList.contains("drawn")) {
      var line = sw.querySelector(".spark-line");
      if (line && !reducedMotion && line.getTotalLength) {
        var L = line.getTotalLength();
        line.style.strokeDasharray = L;
        line.style.strokeDashoffset = L;
        void line.getBoundingClientRect();
        line.style.transition = "stroke-dashoffset 0.45s ease";
        line.style.strokeDashoffset = "0";
      }
      sw.classList.add("drawn");
    }
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
    SIGNALS.forEach(function (s) { left.appendChild(signalBar(a, s)); });

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

    // share affordances: permalink + row-as-markdown (dev-native primitives)
    var actions = el("div", "detail-actions");
    function copyButton(label, makeText) {
      var btn = el("button", null, label);
      btn.type = "button";
      btn.addEventListener("click", function () {
        if (!navigator.clipboard) return;
        navigator.clipboard.writeText(makeText()).then(function () {
          btn.classList.add("copied");
          btn.textContent = "copied ✓";
          setTimeout(function () {
            btn.classList.remove("copied");
            btn.textContent = label;
          }, 1400);
        });
      });
      actions.appendChild(btn);
    }
    function permalink() {
      return location.origin === "null" || location.protocol === "file:"
        ? location.href.split("#")[0] + "#c=" + encodeURIComponent(a.name)
        : location.origin + location.pathname + "#c=" + encodeURIComponent(a.name);
    }
    copyButton("copy link", permalink);
    copyButton("copy as markdown", function () {
      var s = a.signals;
      return "| contributor | tier | impact | own | surv | coup | rev |\n" +
        "|---|---|---|---|---|---|---|\n" +
        "| " + a.name + " | T" + a.tier + " | " + a.impact.toFixed(3) + " | " +
        s.ownership_concentration.toFixed(2) + " | " +
        s.code_survival_tenure_normalized.toFixed(2) + " | " +
        s.coupling_criticality.toFixed(2) + " | " +
        s.review_leverage.toFixed(2) + " |\n\n" + permalink();
    });
    left.appendChild(actions);

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
    state.showAll = true; // the target row may sit behind the disclosure fold
    render();
    var row = body.querySelector('tr.row[data-name="' + cssEscape(name) + '"]');
    if (!row) return;
    toggleDetail(row, byName[name]);
    row.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "center" });
    var btn = row.querySelector(".row-btn");
    if (btn) btn.focus({ preventScroll: true });
    if (!reducedMotion) {
      row.classList.add("pulse"); // lands as the proxy dot arrives
      setTimeout(function () { row.classList.remove("pulse"); }, 1600);
    }
  }
  function cssEscape(s) {
    return (window.CSS && CSS.escape) ? CSS.escape(s) : s.replace(/["\\]/g, "\\$&");
  }

  /* ------------------------------------------------------------- org lens
     Per-person signals rolled up to the repository: a Lorenz-style
     concentration card (the diagonal makes the Gini visible), single-owner
     hotspot bars, and the three-beat departure simulator. Numbers reconcile
     with compare mode by construction (same is_orphan_risk definition). */
  (function orgLens() {
    var ORG = D.org;
    var host = document.getElementById("org-curve");
    if (!ORG || !host) return;
    var NS = "http://www.w3.org/2000/svg";
    function svgEl(tag, attrs, cls, text) {
      var n = document.createElementNS(NS, tag);
      for (var k in attrs) n.setAttribute(k, attrs[k]);
      if (cls) n.setAttribute("class", cls);
      if (text !== undefined) n.textContent = text;
      return n;
    }
    var WORDS = ["zero", "one", "two", "three", "four", "five", "six",
                 "seven", "eight", "nine", "ten", "eleven", "twelve"];
    function words(n) { return n < WORDS.length ? WORDS[n] : String(n); }
    function cap(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

    // --- Lorenz card: curve + equality diagonal + shaded gap
    var curve = ORG.curve, n = curve.length;
    var W = 560, H = 320, m = { t: 34, r: 34, b: 34, l: 34 };
    var pw = W - m.l - m.r, ph = H - m.t - m.b;
    var X = function (i) { return m.l + (i / (n - 1)) * pw; };
    var Y = function (v) { return m.t + (1 - v) * ph; };
    var kHalf = 0, k10 = Math.min(10, n);
    while (kHalf < n && curve[kHalf] < 0.5) kHalf += 1;
    kHalf += 1; // 1-based count of people to reach half
    var svg = svgEl("svg", { viewBox: "0 0 " + W + " " + H, role: "img" });
    svg.setAttribute("aria-label",
      (kHalf === 1 ? "One contributor holds"
                   : cap(words(kHalf)) + " contributors hold") +
      " over half the surviving code; the top " +
      k10 + " hold " + Math.round(curve[k10 - 1] * 100) +
      "%. The dashed diagonal shows an evenly spread codebase.");
    var pts = curve.map(function (v, i) {
      return X(i).toFixed(1) + "," + Y(v).toFixed(1);
    });
    // shaded gap between the curve and the equality diagonal
    var gap = "M " + pts.join(" L ") + " L " +
      curve.map(function (_, i) {
        var j = n - 1 - i;
        return X(j).toFixed(1) + "," + Y((j + 1) / n).toFixed(1);
      }).join(" L ") + " Z";
    svg.appendChild(svgEl("line",
      { x1: m.l, y1: Y(0), x2: W - m.r, y2: Y(0) }, "org-axis"));
    svg.appendChild(svgEl("line",
      { x1: m.l, y1: m.t, x2: m.l, y2: Y(0) }, "org-axis"));
    svg.appendChild(svgEl("path", { d: gap }, "org-gap"));
    svg.appendChild(svgEl("line",
      { x1: m.l, y1: Y(0), x2: W - m.r, y2: m.t }, "org-diag"));
    svg.appendChild(svgEl("polyline",
      { points: pts.join(" "), fill: "none" }, "org-curve-line"));
    // dedupe by k (on a solo-cliff repo, top-1 IS the half marker) and clamp
    // labels inside the plot (the curve plateaus at the top edge)
    var seen = {};
    [[1, "top 1 · "], [kHalf, "top " + words(kHalf) + " · "], [k10, "top " + k10 + " · "]]
      .forEach(function (mk) {
        var k = mk[0];
        if (seen[k]) return;
        seen[k] = true;
        var x = X(k - 1), y = Y(curve[k - 1]);
        svg.appendChild(svgEl("circle", { cx: x, cy: y, r: 4 }, "org-dot"));
        svg.appendChild(svgEl("text",
          { x: x + 9, y: Math.max(m.t + 12, y - 2) }, "org-mark",
          mk[1] + Math.round(curve[k - 1] * 100) + "%"));
      });
    svg.appendChild(svgEl("text",
      { x: W - m.r, y: Y(0) + 18, "text-anchor": "end" }, "org-axlab",
      "contributors, ranked by surviving lines →"));
    svg.appendChild(svgEl("text",
      { x: m.l - 6, y: m.t - 10 }, "org-axlab",
      "↑ cumulative share of surviving code"));
    svg.appendChild(svgEl("text",
      { x: W - m.r - 8, y: m.t + 64, "text-anchor": "end" }, "org-diaglab",
      "· · · an evenly spread codebase"));
    host.appendChild(svg);
    var headline = document.getElementById("org-headline");
    headline.appendChild(document.createTextNode(
      kHalf === 1 ? "One person holds " : cap(words(kHalf)) + " people hold "));
    headline.appendChild(el("b", null, "over half"));
    headline.appendChild(document.createTextNode(" the surviving code."));
    document.getElementById("org-hsub").textContent =
      "top " + k10 + " hold " + Math.round(curve[k10 - 1] * 100) + "% · Gini " +
      ORG.gini.toFixed(2) + " across all " + n + " contributors";

    // --- hotspot bars
    var hotHost = document.getElementById("org-hotspots");
    ORG.hotspots.forEach(function (h) {
      var share = Math.round(h.orphans / h.files * 100);
      var row = el("div", "hb");
      row.appendChild(el("span", "hb-dir", h.dir));
      var track = el("span", "hb-track");
      var fill = el("span", "hb-fill");
      fill.style.width = share + "%";
      track.appendChild(fill);
      row.appendChild(track);
      var val = el("span", "hb-val", share + "% ");
      val.appendChild(el("small", null, "(" + h.orphans + " of " + h.files + ")"));
      row.appendChild(val);
      hotHost.appendChild(row);
    });

    // --- departure simulator: three honest beats
    var sel = document.getElementById("sim-select");
    var readout = document.getElementById("sim-readout");
    var names = Object.keys(ORG.risk).sort(function (a, b) {
      return ORG.risk[b].files - ORG.risk[a].files;
    });
    names.forEach(function (name) {
      var o = el("option", null, name);
      o.value = name;
      sel.appendChild(o);
    });
    function pctShare(p) { return p < 0.01 ? "<1%" : "~" + Math.round(p * 100) + "%"; }
    function renderSim(name) {
      var r = ORG.risk[name];
      if (!r) return;
      readout.textContent = "";
      var b1 = el("p", "sim-beat1");
      b1.appendChild(el("b", null, plural(r.files, "file")));
      b1.appendChild(document.createTextNode(
        " lose their only major owner — carrying "));
      b1.appendChild(el("b", null, pctShare(r.cen_share)));
      b1.appendChild(document.createTextNode(
        " of the co-change graph's centrality. Most central: "));
      var mono = el("span", "sim-mono");
      mono.textContent = r.top.map(function (p2) {
        return middleTruncate(p2, 38);
      }).join(", ");
      mono.title = r.top.join("\n");
      b1.appendChild(mono);
      b1.appendChild(document.createTextNode("."));
      readout.appendChild(b1);
      if (r.no_second > 0) {
        readout.appendChild(el("p", "sim-beat2",
          r.no_second + " of them have no other contributor at all."));
      }
      var b3 = el("p", "sim-beat3");
      if (r.nearest.length) {
        b3.appendChild(document.createTextNode("Nearest others: "));
        r.nearest.forEach(function (s, i) {
          if (i) b3.appendChild(document.createTextNode(", "));
          b3.appendChild(el("b", null, s.name));
          b3.appendChild(document.createTextNode(
            i === 0 ? " (best-placed second on " + plural(s.files, "file") + ")"
                    : " (" + s.files + ")"));
        });
        var med = (ORG.median_second || 0) * 100;
        b3.appendChild(document.createTextNode(med > 0
          ? " — though a typical second contributor holds just " +
            (med < 1 ? "under 1%" : "~" + Math.round(med) + "%") + " of the code. "
          : ". "));
      } else {
        b3.appendChild(document.createTextNode(
          "No other contributor has touched any of these files. "));
      }
      var back = el("button", "pointer-link sim-back", "view their row →");
      back.type = "button";
      back.addEventListener("click", function () { jumpToAuthor(name); });
      b3.appendChild(back);
      readout.appendChild(b3);
    }
    sel.addEventListener("change", function () { renderSim(sel.value); });
    if (names.length) { sel.value = names[0]; renderSim(names[0]); }

    orgSimSet = function (name) { // row ⚠ badge entry point
      if (!ORG.risk[name]) return;
      sel.value = name;
      renderSim(name);
      document.getElementById("team").scrollIntoView(
        { behavior: reducedMotion ? "auto" : "smooth", block: "start" });
    };
  })();

  /* ------------------------------------------------------------ hash state
     The URL is a contract: #c=<name>&view=<id>&sort=<key>.<a|d>, defaults
     omitted. pushState for contributor selection (a navigation act),
     replaceState for refinements (sort, view). */
  (function hashState() {
    var applying = false;
    function serialize() {
      var parts = [];
      if (openName) parts.push("c=" + encodeURIComponent(openName));
      if (currentFieldView !== "spectrum") parts.push("view=" + currentFieldView);
      if (!(state.key === "rank" && state.dir === 1) && state.key !== "mix") {
        // mixer weights aren't serialized, so a mix-sorted URL would be a
        // broken contract — the hash stays about the published data
        parts.push("sort=" + state.key + "." + (state.dir === 1 ? "a" : "d"));
      }
      var pair = compareGetPair && compareGetPair();
      if (pair) parts.push("cmp=" + pair.map(encodeURIComponent).join(","));
      return parts.length ? "#" + parts.join("&") : "";
    }
    writeHash = function (push) {
      if (applying) return;
      var h = serialize();
      var url = h || location.pathname + location.search;
      if (push) history.pushState(null, "", url);
      else history.replaceState(null, "", url);
    };
    onFieldViewChange = function (id) {
      currentFieldView = id;
      if (!applying) writeHash(false);
    };
    hashSetC = function (name) { // tap-to-pin: selection without expansion
      if (!applying) {
        history.replaceState(null, "",
          "#c=" + encodeURIComponent(name));
      }
    };
    function apply() {
      var h = location.hash.replace(/^#/, "");
      if (applying) return;
      applying = true;
      try {
        var params = {};
        h.split("&").forEach(function (kv) {
          var i = kv.indexOf("=");
          if (i > 0) params[kv.slice(0, i)] = decodeURIComponent(kv.slice(i + 1));
        });
        var view = params.view || "spectrum";
        if (setFieldView && view !== currentFieldView &&
            ["spectrum", "activity", "signals", "tiers"].indexOf(view) !== -1) {
          setFieldView(view);
        }
        var sort = (params.sort || "rank.a").split(".");
        var key = sort[0], dir = sort[1] === "d" ? -1 : 1;
        if (key !== state.key || dir !== state.dir) {
          state.key = key; state.dir = dir;
          render();
        }
        if (params.c && byName[params.c]) {
          if (openName !== params.c) jumpToAuthor(params.c);
        } else if (openName) {
          closeDetail();
        }
        if (params.cmp && compareApply) {
          var pr = params.cmp.split(",");
          if (pr.length === 2) compareApply(pr[0], pr[1]);
        } else if (compareClose) {
          compareClose(); // no cmp in the hash (e.g. back button) -> ensure closed
        }
      } finally {
        applying = false;
      }
    }
    window.addEventListener("hashchange", apply);
    window.addEventListener("popstate", apply);
    // defer past all synchronous module init: the board's initial render()
    // runs at the end of this file and would wipe a detail opened here
    if (location.hash.length > 1) requestAnimationFrame(apply);
  })();

  /* -------------------------------------------------- quote word-fill */
  (function quoteFill() {
    var q = document.getElementById("quote-line");
    if (!q) return;
    var words = q.textContent.split(/(\s+)/);
    q.textContent = "";
    var spans = [];
    words.forEach(function (w) {
      if (/^\s+$/.test(w)) {
        q.appendChild(document.createTextNode(w));
      } else if (w) {
        var s = el("span", "w", w);
        q.appendChild(s);
        spans.push(s);
      }
    });
    if (reducedMotion) {
      spans.forEach(function (s) { s.classList.add("lit"); });
      return;
    }
    var ticking = false;
    function update() { // bidirectional scrub, matching the finale
      ticking = false;
      var r = q.getBoundingClientRect();
      var vh = window.innerHeight;
      if (r.top > vh || r.bottom < 0) return; // off-screen: nothing to do
      var t = (vh * 0.82 - r.top) / (vh * 0.5);
      t = Math.max(0, Math.min(1, t));
      var lit = Math.round(t * spans.length);
      spans.forEach(function (s, i) { s.classList.toggle("lit", i < lit); });
    }
    function onScroll() {
      if (!ticking) { ticking = true; requestAnimationFrame(update); }
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    update();
  })();

  /* -------------------------------------------------- reveals + count-up */
  function countUp(node) {
    var target = parseInt(node.dataset.count, 10);
    var text = node.dataset.text || String(target);
    if (reducedMotion || !target || target < 10) { node.textContent = text; return; }
    var t0 = performance.now(), DUR = 700;
    (function tick(now) {
      var t = Math.min((now - t0) / DUR, 1);
      var e = 1 - Math.pow(1 - t, 3);
      node.textContent = Math.round(target * e).toLocaleString("en-US");
      if (t < 1) requestAnimationFrame(tick);
      else node.textContent = text;
    })(t0);
  }
  (function reveals() {
    var els = document.querySelectorAll("[data-reveal]");
    function fire(target) {
      target.classList.add("in");
      target.querySelectorAll(".tile-value[data-count]").forEach(countUp);
      if (target.dataset.count !== undefined) countUp(target);
    }
    if (!("IntersectionObserver" in window) || reducedMotion) {
      els.forEach(function (n) { fire(n); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        // already deep in view when the entry fires (fast scroll, anchor
        // jump): appear near-instantly instead of making the reader wait
        if (e.intersectionRatio > 0.9 ||
            e.boundingClientRect.top < window.innerHeight * 0.55) {
          e.target.classList.add("in-fast");
        }
        fire(e.target);
        io.unobserve(e.target);
      });
    }, { threshold: 0.05 });
    els.forEach(function (n) { io.observe(n); });
    // safety net: content must never stay hidden if an observation is missed
    // (print, find-in-page, programmatic capture, exotic scrolling)
    setTimeout(function () {
      els.forEach(function (n) {
        if (!n.classList.contains("in")) fire(n);
      });
      io.disconnect();
    }, 3000);
  })();

  /* ------------------------------------------------------- nav elevation */
  (function navElevation() {
    var nav = document.querySelector(".nav");
    if (!nav) return;
    var ticking = false;
    function update() {
      ticking = false;
      nav.classList.toggle("scrolled", window.scrollY > 8);
    }
    window.addEventListener("scroll", function () {
      if (!ticking) { ticking = true; requestAnimationFrame(update); }
    }, { passive: true });
    update();
  })();

  /* --------------------------------------------------------- arc parallax
     two planes: arcs drift at 0.06, the hero content at 0.025 (NOT .formula —
     it carries data-reveal, whose transform the reveal system owns) */
  (function arcParallax() {
    if (reducedMotion) return;
    var arcs = document.querySelector(".hero-arcs");
    var inner = document.querySelector(".hero-inner");
    var hero = document.querySelector(".hero");
    if (!arcs || !hero) return;
    var ticking = false;
    function update() {
      ticking = false;
      var y = window.scrollY;
      if (y > hero.offsetHeight) return; // hero off-screen: leave it be
      arcs.style.transform = "translateY(" + (y * 0.06).toFixed(1) + "px)";
      if (inner) inner.style.transform = "translateY(" + (y * 0.025).toFixed(1) + "px)";
    }
    window.addEventListener("scroll", function () {
      if (!ticking) { ticking = true; requestAnimationFrame(update); }
    }, { passive: true });
  })();

  /* -------------------------------------------------------- finale scrub
     The espresso arcs draw as the footer enters: the co-change graph
     converging under "Signals, not verdicts" — the page's one big payoff.
     Scrubbed both directions; per-arc stagger via --i (set at build). */
  (function finaleScrub() {
    var svg = document.querySelector(".espresso-arcs");
    var foot = document.querySelector(".espresso");
    if (!svg || !foot) return;
    var paths = [].slice.call(svg.querySelectorAll("path"));
    if (reducedMotion || !paths.length) return; // reduced-motion CSS pins them drawn
    var ticking = false;
    var inner = foot.querySelector(".espresso-inner");
    function update() {
      ticking = false;
      var r = foot.getBoundingClientRect();
      var vh = window.innerHeight;
      if (r.top > vh || r.bottom < 0) return; // off-screen, nothing to scrub
      var travel = Math.min(r.height, vh) * 0.85;
      var raw = (vh - r.top) / travel;
      paths.forEach(function (p, i) {
        var t = Math.max(0, Math.min(1, raw - i * 0.005));
        p.style.strokeDashoffset = (1 - t).toFixed(4);
      });
      if (inner) { // content rises to meet the converging arcs
        inner.style.transform =
          "translateY(" + ((1 - Math.min(raw, 1)) * 14).toFixed(1) + "px)";
      }
    }
    window.addEventListener("scroll", function () {
      if (!ticking) { ticking = true; requestAnimationFrame(update); }
    }, { passive: true });
    window.addEventListener("resize", function () {
      if (!ticking) { ticking = true; requestAnimationFrame(update); }
    });
    update();
  })();

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

  // print should show the whole table, not the disclosure fold
  window.addEventListener("beforeprint", function () {
    if (!state.showAll) { state.showAll = true; render(); }
  });

  /* --------------------------------------------------- prologue: predict ρ
     A non-blocking gut-check above the hero: the visitor scrubs a scatter from
     a random cloud toward a straight line to guess how tightly commits track
     impact, then reveals the real data (D.meta.rho). Ships hidden without JS and
     renders a static reveal under reduced motion. Self-contained: it never
     touches the field engine. */
  (function prologue() {
    var root = document.getElementById("prologue");
    if (!root || AUTHORS.length < 4) return;
    var host = document.getElementById("prologue-svg");
    var range = document.getElementById("prologue-range");
    var revealBtn = document.getElementById("prologue-reveal");
    var controls = root.querySelector(".prologue-controls");
    var result = document.getElementById("prologue-result");
    var readout = document.getElementById("prologue-readout");
    if (!host || !range || !revealBtn || !controls || !result || !readout) return;

    var NS = "http://www.w3.org/2000/svg";
    var W = 640, H = 340, m = { t: 22, r: 22, b: 30, l: 30 };
    var pw = W - m.l - m.r, ph = H - m.t - m.b;
    var PX = function (x) { return m.l + x * pw; };
    var PY = function (y) { return m.t + y * ph; };
    var RHO = D.meta.rho; // measured commits↔impact Spearman, from the payload
    var N = AUTHORS.length;
    var RAMP = ["#EC9E74", "#DF7647", "#CB5124", "#A63C15", "#78290C"];
    function rampColor(t) {
      t = Math.max(0, Math.min(1, t)) * (RAMP.length - 1);
      var i = Math.min(Math.floor(t), RAMP.length - 2), f = t - i;
      function ch(hex, o) { return parseInt(hex.substr(o, 2), 16); }
      var c = [1, 3, 5].map(function (o) {
        return Math.round(ch(RAMP[i], o) + (ch(RAMP[i + 1], o) - ch(RAMP[i], o)) * f);
      });
      return "rgb(" + c.join(",") + ")";
    }
    function hash01(i) { return ((i * 2654435761) % 100003) / 100003; }

    // real coords reused from the activity view (x = commits on a log axis,
    // y = impact, both normalized 0..1). ry = a decorrelated shuffle of the
    // impacts (the "random cloud" anchor); ly = a near-perfect line.
    var pts = AUTHORS.map(function (a, i) {
      return { a: a, x: a.views.activity[0], ty: a.views.activity[1],
               imp: N > 1 ? 1 - (a.rank - 1) / (N - 1) : 1, i: i };
    });
    var tys = pts.map(function (p) { return p.ty; });
    pts.map(function (_, i) { return i; })
      .sort(function (x, y) { return hash01(x + 7) - hash01(y + 7); })
      .forEach(function (src, k) { pts[k].ry = tys[src]; });
    pts.forEach(function (p) {
      p.ly = Math.max(0.04, Math.min(0.96, (1 - p.x) + (hash01(p.i + 3) - 0.5) * 0.07));
    });

    function svgEl(tag, attrs, cls) {
      var n = document.createElementNS(NS, tag);
      for (var k in attrs) n.setAttribute(k, attrs[k]);
      if (cls) n.setAttribute("class", cls);
      return n;
    }
    var svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    svg.setAttribute("aria-hidden", "true"); // the host carries the labelled summary
    svg.appendChild(svgEl("line",
      { x1: m.l, y1: PY(1), x2: W - m.r, y2: PY(1) }, "prologue-axis"));
    svg.appendChild(svgEl("line",
      { x1: m.l, y1: m.t, x2: m.l, y2: PY(1) }, "prologue-axis"));
    var xlab = svgEl("text",
      { x: W - m.r, y: PY(1) + 20, "text-anchor": "end" }, "prologue-axlab");
    xlab.textContent = "more commits →";
    svg.appendChild(xlab);
    var ylab = svgEl("text",
      { x: m.l - 4, y: m.t - 8, "text-anchor": "start" }, "prologue-axlab");
    ylab.textContent = "↑ more impact";
    svg.appendChild(ylab);
    pts.forEach(function (p) {
      var g = svgEl("g", {}, "prologue-dot");
      var r = (2.6 + 3.4 * Math.pow(p.imp, 1.5)) * (D.field.rscale || 1);
      g.appendChild(svgEl("circle", { r: r.toFixed(1), fill: rampColor(p.imp) }));
      p.g = g;
      svg.appendChild(g);
    });
    host.appendChild(svg);

    function place(p, y) {
      p.g.style.transform =
        "translate(" + PX(p.x).toFixed(1) + "px," + PY(y).toFixed(1) + "px)";
    }
    function layout(g) {
      pts.forEach(function (p) { place(p, g * p.ly + (1 - g) * p.ry); });
    }

    var revealed = false;
    function reveal() {
      if (revealed) return;
      revealed = true;
      var g = parseFloat(range.value);
      // cascade to the truth, highest-impact dots landing first
      pts.slice().sort(function (a, b) { return b.imp - a.imp; })
        .forEach(function (p, k) {
          p.g.style.transitionDelay = (k * 6) + "ms";
          p.g.style.transitionDuration = "820ms";
        });
      pts.forEach(function (p) { place(p, p.ty); });
      range.disabled = true;
      controls.classList.add("done");
      revealBtn.hidden = true;
      readout.textContent =
        "You guessed ρ ≈ " + g.toFixed(2) + ".  The real correlation is " + RHO.toFixed(2) + ".";
      result.hidden = false;
    }

    root.hidden = false; // progressive enhancement: shown only once JS runs

    if (reducedMotion) {
      // static reveal — skip the guessing choreography entirely
      controls.hidden = true;
      revealBtn.hidden = true;
      pts.forEach(function (p) { place(p, p.ty); });
      readout.textContent =
        "Commits and impact correlate at ρ = " + RHO.toFixed(2) +
        " — strong, but not a straight line.";
      result.hidden = false;
      return;
    }

    layout(parseFloat(range.value)); // initial positions before transitions arm
    requestAnimationFrame(function () { host.classList.add("prologue-live"); });
    range.addEventListener("input", function () {
      if (!revealed) layout(parseFloat(range.value));
    });
    revealBtn.addEventListener("click", reveal);
  })();

  /* ------------------------------------------------------------- compare
     Pin two contributors and hold them side by side. The dialog marks where
     each *leads* a signal but never crowns a winner ("signals, not verdicts";
     within-tier order is meaningless) and frames the synthesis around the
     shared surface + bus-factor — the real "hard to replace" question. */
  (function compare() {
    var tray = document.getElementById("compare-tray");
    var slotsEl = document.getElementById("compare-slots");
    var openBtn = document.getElementById("compare-open");
    var clearBtn = document.getElementById("compare-clear");
    var modal = document.getElementById("compare");
    var backdrop = document.getElementById("compare-backdrop");
    var closeBtn = document.getElementById("compare-close");
    var bodyEl = document.getElementById("compare-body");
    if (!tray || !slotsEl || !openBtn || !modal || !bodyEl) return;

    var FILES = D.files_shared || [];
    var selected = [];      // up to two names
    var dialogOpen = false;
    var lastFocus = null;

    function firstName(n) { return n.split(/\s+/)[0]; }
    function baseName(p) { return p.split("/").pop(); }
    function has(name) { return selected.indexOf(name) !== -1; }

    function markRows() {
      Array.prototype.forEach.call(document.querySelectorAll(".row-compare"),
        function (b) {
          var on = has(b.dataset.name);
          b.setAttribute("aria-pressed", on ? "true" : "false");
          var row = b.closest(".row");
          if (row) row.classList.toggle("comparing", on);
        });
    }

    function renderTray() {
      slotsEl.textContent = "";
      selected.forEach(function (name) {
        var chip = el("span", "compare-chip");
        chip.appendChild(el("span", "compare-chip-mono", monogramText(name)));
        chip.appendChild(el("span", "compare-chip-name", name));
        var x = el("button", "compare-chip-x", "✕");
        x.type = "button";
        x.setAttribute("aria-label", "Remove " + name);
        x.addEventListener("click", function () { toggle(name); });
        chip.appendChild(x);
        slotsEl.appendChild(chip);
      });
      if (selected.length < 2) {
        slotsEl.appendChild(el("span", "compare-slot-empty",
          selected.length ? "pick one more" : "pick two contributors"));
      }
      openBtn.disabled = selected.length !== 2;
      tray.hidden = selected.length === 0;
    }

    function toggle(name) {
      if (!byName[name]) return;
      var i = selected.indexOf(name);
      if (i !== -1) selected.splice(i, 1);
      else {
        if (selected.length >= 2) selected.shift(); // keep the two most recent
        selected.push(name);
      }
      renderTray();
      markRows();
      if (dialogOpen && selected.length === 2) fillDialog();
      else if (dialogOpen) closeDialog();
      writeHash(false);
    }

    function column(a, other) {
      var col = el("div", "compare-col");
      var head = el("div", "compare-col-head");
      head.appendChild(el("span",
        "monogram" + (a.tier === 1 ? " t1" : ""), monogramText(a.name)));
      var meta = el("div", "compare-col-meta");
      meta.appendChild(el("div", "compare-col-name", a.name));
      meta.appendChild(el("div", "compare-col-sub",
        "T" + a.tier + " · impact " + a.impact.toFixed(3) + " · rank " + a.rank));
      head.appendChild(meta);
      col.appendChild(head);
      SIGNALS.forEach(function (s) {
        var lead = a.signals[s.key] > other.signals[s.key] + 1e-9;
        col.appendChild(signalBar(a, s, { lead: lead, short: true }));
      });
      var rl = el("p", "compare-review");
      if (a.review) {
        rl.appendChild(el("b", null, String(a.review.count)));
        rl.appendChild(document.createTextNode(" reviews · " +
          a.review.distinct_authors + " authors"));
      } else {
        rl.textContent = "no PR reviews on record";
      }
      col.appendChild(rl);
      return col;
    }

    function intersect(x, y) {
      var set = {}, all = [];
      x.forEach(function (i) { set[i] = 1; });
      y.forEach(function (i) { if (set[i]) all.push(i); });
      // prefer real source files (in a subdir, not a root dotfile) as examples
      var pref = all.filter(function (i) {
        var f = FILES[i]; return f.indexOf("/") !== -1 && f.charAt(0) !== ".";
      });
      return { n: all.length, egs: (pref.length ? pref : all).slice(0, 3) };
    }

    function readout(a, b, shared) {
      var parts = [];
      if (a.tier === b.tier) parts.push("Same tier — the score gap between them is noise.");
      var oa = a.owned.orphan, ob = b.owned.orphan;
      if (!oa && !ob) {
        parts.push("Neither is the sole owner of any file — low bus-factor either way.");
      } else {
        var hi = oa >= ob ? a : b, hn = Math.max(oa, ob), ln = Math.min(oa, ob);
        parts.push(firstName(hi.name) + " is the sole major owner of " + hn + " files" +
          (ln ? " to " + firstName((oa >= ob ? b : a).name) + "'s " + ln : "") +
          " — the heavier bus-factor risk.");
      }
      if (shared) parts.push(shared + " co-owned files mean that surface isn't siloed.");
      return parts.join(" ");
    }

    function synthesis(a, b) {
      var wrap = el("div", "compare-synth");
      wrap.appendChild(el("h3", "compare-synth-h", "Shared surface & bus-factor"));
      var inter = intersect(a.owned.shared || [], b.owned.shared || []);
      var line = el("p", "compare-synth-line");
      line.appendChild(el("b", null, String(inter.n)));
      line.appendChild(document.createTextNode(" files co-owned by both"));
      if (inter.egs.length) {
        line.appendChild(document.createTextNode(" · e.g. " +
          inter.egs.map(function (i) { return baseName(FILES[i]); }).join(", ")));
      }
      wrap.appendChild(line);
      var cols = el("div", "compare-synth-cols");
      [a, b].forEach(function (p) {
        var c = el("div", "compare-synth-col");
        c.appendChild(el("b", null, String(p.owned.orphan)));
        c.appendChild(document.createTextNode(" sole-owned by " + firstName(p.name)));
        cols.appendChild(c);
      });
      wrap.appendChild(cols);
      wrap.appendChild(el("p", "compare-readout", readout(a, b, inter.n)));
      return wrap;
    }

    function fillDialog() {
      var a = byName[selected[0]], b = byName[selected[1]];
      if (!a || !b) return;
      bodyEl.textContent = "";
      var cols = el("div", "compare-cols");
      cols.appendChild(column(a, b));
      cols.appendChild(column(b, a));
      bodyEl.appendChild(cols);
      bodyEl.appendChild(synthesis(a, b));
      // grow the bars from 0 (matches the detail panel's open animation)
      bodyEl.querySelectorAll(".dbar .fill").forEach(function (f) {
        if (f.dataset.w) f.style.setProperty("--w", f.dataset.w);
      });
    }

    var FOCUSABLE = 'button, [href], input, [tabindex]:not([tabindex="-1"])';
    function trap(ev) {
      if (ev.key !== "Tab") return;
      var f = modal.querySelectorAll(FOCUSABLE);
      if (!f.length) return;
      var first = f[0], last = f[f.length - 1];
      if (ev.shiftKey && document.activeElement === first) { ev.preventDefault(); last.focus(); }
      else if (!ev.shiftKey && document.activeElement === last) { ev.preventDefault(); first.focus(); }
    }

    function openDialog(push, invoker) {
      if (selected.length !== 2) return;
      // pass the invoker explicitly: WebKit doesn't focus a <button> on click,
      // so document.activeElement would be <body> and focus wouldn't restore
      lastFocus = invoker || document.activeElement;
      fillDialog();
      modal.hidden = false;
      dialogOpen = true;
      document.body.classList.add("compare-lock");
      closeBtn.focus();
      modal.addEventListener("keydown", trap);
      if (push !== false) writeHash(true);
    }
    function closeDialog(silent) {
      if (!dialogOpen) return;
      dialogOpen = false;
      modal.hidden = true;
      modal.removeEventListener("keydown", trap);
      document.body.classList.remove("compare-lock");
      if (lastFocus && lastFocus.focus) lastFocus.focus();
      if (!silent) writeHash(false);
    }

    openBtn.addEventListener("click", function () { openDialog(true, openBtn); });
    clearBtn.addEventListener("click", function () {
      selected = []; renderTray(); markRows();
      if (dialogOpen) closeDialog(); else writeHash(false);
    });
    closeBtn.addEventListener("click", function () { closeDialog(); });
    backdrop.addEventListener("click", function () { closeDialog(); });

    compareToggle = toggle;
    compareHas = has;
    compareGetPair = function () {
      return dialogOpen && selected.length === 2 ? selected.slice() : null;
    };
    compareApply = function (a, b) { // from a #cmp deep-link
      if (!byName[a] || !byName[b] || a === b) return;
      selected = [a, b];
      renderTray(); markRows();
      openDialog(false); // the hash is already the source of truth; don't re-push
    };
    compareClose = function () { return dialogOpen ? (closeDialog(), true) : false; };

    renderTray();
  })();

  /* ------------------------------------------------------- global keyboard */
  var eggBuf = "";
  document.addEventListener("keydown", function (ev) {
    var typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
    // easter egg: type "gravity" anywhere outside a text field
    if (!typing && ev.key && ev.key.length === 1) {
      eggBuf = (eggBuf + ev.key.toLowerCase()).slice(-7);
      if (eggBuf === "gravity" && fieldGravity) { eggBuf = ""; fieldGravity(); }
    }
    if (ev.key === "/" && !typing) {
      ev.preventDefault();
      search.focus();
    } else if (ev.key === "Escape") {
      if (compareClose && compareClose()) { return; } // modal first
      if (fieldGravity && fieldGravity.isOn()) { fieldGravity.off(); tipHide(); return; }
      if (typing && search.value) {
        search.value = ""; state.query = ""; render();
      } else {
        closeDetail();
      }
      tipHide();
    }
  });

  render();

  // a small hidden delight for anyone poking around in the console
  if (!reducedMotion) {
    try { console.log("%c↯ psst — type “gravity”", "color:#CB5124;font-weight:600"); }
    catch (e) { /* console-less environments */ }
  }
})();
