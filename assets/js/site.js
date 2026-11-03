/* Progressive enhancement only: the page is fully usable without this file. */
(function () {
  document.documentElement.classList.remove("no-js");

  // Mobile menu
  var toggle = document.querySelector(".nav-toggle");
  var list = document.getElementById("nav-list");
  if (toggle && list) {
    toggle.addEventListener("click", function () {
      var open = toggle.getAttribute("aria-expanded") === "true";
      toggle.setAttribute("aria-expanded", String(!open));
      list.classList.toggle("open", !open);
    });
    list.addEventListener("click", function (e) {
      if (e.target.closest("a")) { toggle.setAttribute("aria-expanded", "false"); list.classList.remove("open"); }
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && list.classList.contains("open")) { toggle.click(); toggle.focus(); }
    });
  }

  // Accessible tabs (WAI-ARIA pattern, automatic activation)
  document.querySelectorAll("[data-tabs]").forEach(function (box) {
    var tabs = Array.prototype.slice.call(box.querySelectorAll('[role="tab"]'));
    function select(tab, focus) {
      tabs.forEach(function (t) {
        var on = t === tab;
        t.setAttribute("aria-selected", String(on));
        t.tabIndex = on ? 0 : -1;
        document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
      });
      if (focus) tab.focus();
    }
    tabs.forEach(function (t, i) {
      t.addEventListener("click", function () { select(t, false); });
      t.addEventListener("keydown", function (e) {
        var n = null;
        if (e.key === "ArrowRight") n = tabs[(i + 1) % tabs.length];
        if (e.key === "ArrowLeft") n = tabs[(i - 1 + tabs.length) % tabs.length];
        if (e.key === "Home") n = tabs[0];
        if (e.key === "End") n = tabs[tabs.length - 1];
        if (n) { e.preventDefault(); select(n, true); }
      });
    });
    // Deep links such as #votes open the right tab
    function fromHash() {
      var t = tabs.find(function (t) { return "#" + t.getAttribute("aria-controls") === location.hash; });
      if (t) { select(t, false); }
      return t;
    }
    if (!fromHash()) select(tabs[0], false);
    window.addEventListener("hashchange", fromHash);
  });

  // Diary: upcoming / past toggle
  var seg = document.querySelectorAll(".seg-btn");
  seg.forEach(function (b) {
    b.addEventListener("click", function () {
      seg.forEach(function (x) {
        var on = x === b;
        x.setAttribute("aria-pressed", String(on));
        var p = document.querySelector('[data-panel="' + x.dataset.show + '"]');
        if (p) p.hidden = !on;
      });
    });
  });

  // Gallery lightbox
  var lb = document.getElementById("lightbox");
  if (lb && lb.showModal) {
    document.querySelectorAll(".g-open").forEach(function (b) {
      b.addEventListener("click", function () {
        lb.querySelector("img").src = b.dataset.src;
        lb.querySelector("img").alt = b.dataset.alt;
        lb.querySelector("p").textContent = b.dataset.cap || "";
        lb.showModal();
      });
    });
    lb.addEventListener("click", function (e) { if (e.target === lb) lb.close(); });
  }

  // Crime map – loads Leaflet and OSM tiles only when asked
  var mb = document.getElementById("load-map");
  if (mb) {
    mb.addEventListener("click", function () {
      mb.disabled = true; mb.textContent = "Loading map…";
      var css = document.createElement("link");
      css.rel = "stylesheet"; css.href = "assets/vendor/leaflet/leaflet.css";
      document.head.appendChild(css);
      var s = document.createElement("script");
      s.src = "assets/vendor/leaflet/leaflet.js";
      s.onload = function () {
        fetch("data/police_map.json?v=" + Date.now()).then(function (r) { return r.json(); }).then(draw)
          .catch(function () { mb.textContent = "Sorry, the map couldn't load"; });
      };
      document.body.appendChild(s);
    });
  }
  function draw(data) {
    var el = document.getElementById("crime-map");
    el.hidden = false; mb.hidden = true;
    var map = L.map(el, { scrollWheelZoom: false });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);
    var group = L.featureGroup().addTo(map);
    (data.boundaries || []).forEach(function (b) {
      if (b.points && b.points.length) L.polygon(b.points, { color: "#14284b", weight: 2, fillOpacity: 0.04 }).bindTooltip(b.name).addTo(group);
    });
    var counts = {};
    (data.points || []).forEach(function (p) {
      var k = p[0] + "," + p[1];
      counts[k] = counts[k] || { lat: p[0], lng: p[1], n: 0, cats: {} };
      counts[k].n++; counts[k].cats[p[2]] = (counts[k].cats[p[2]] || 0) + 1;
    });
    Object.keys(counts).forEach(function (k) {
      var c = counts[k];
      var txt = Object.keys(c.cats).map(function (x) { return (data.categories[x] || x) + ": " + c.cats[x]; }).join("<br>");
      L.circleMarker([c.lat, c.lng], { radius: Math.min(4 + Math.sqrt(c.n) * 2, 16), color: "#fff", weight: 2, fillColor: "#2a78d6", fillOpacity: 0.85 })
        .bindPopup("<strong>" + c.n + " report" + (c.n > 1 ? "s" : "") + "</strong><br>" + txt).addTo(map);
    });
    if (group.getLayers().length) map.fitBounds(group.getBounds(), { padding: [10, 10] });
    else map.setView([52.512, -2.09], 13);
  }
})();
