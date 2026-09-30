(() => {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const safeUrl = (u) => (/^https?:\/\//i.test(u) ? u : "#");
  const REGIONS = ["Europe", "Middle East", "Asia", "Americas", "Africa", "Global"];
  let DATA, region = "All";

  const ago = (iso) => {
    if (!iso) return "";
    const m = Math.round((Date.now() - new Date(iso)) / 60000);
    if (m < 1) return "just now";
    if (m < 60) return m + " min ago";
    if (m < 1440) return Math.round(m / 60) + " h ago";
    return Math.round(m / 1440) + " d ago";
  };
  const fmt = (v, d) => Number(v).toLocaleString("en-GB", { minimumFractionDigits: d, maximumFractionDigits: d });
  const digits = (v) => (Math.abs(v) >= 1000 ? 0 : Math.abs(v) >= 100 ? 2 : 4);
  const pct = (p) => (p == null ? "–" : (p > 0 ? "+" : "") + p.toFixed(2) + "%");
  const cls = (p) => (p == null || Math.abs(p) < 0.005 ? "flat" : p > 0 ? "up" : "down");

  function spark(vals, p) {
    if (!vals || vals.length < 2) return '<svg class="spark"></svg>';
    const w = 76, h = 26, min = Math.min(...vals), max = Math.max(...vals), r = max - min || 1;
    const pts = vals.map((v, i) => `${((i / (vals.length - 1)) * w).toFixed(1)},${(h - 2 - ((v - min) / r) * (h - 4)).toFixed(1)}`).join(" ");
    const c = cls(vals[vals.length - 1] - vals[0]);
    const col = c === "up" ? "var(--up)" : c === "down" ? "var(--down)" : "var(--muted)";
    return `<svg class="spark" viewBox="0 0 ${w} ${h}" aria-hidden="true"><polyline fill="none" stroke="${col}" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round" points="${pts}"/></svg>`;
  }

  // section helper: returns data, or renders an "unavailable" note
  const sec = (k) => DATA.sections[k];
  const note = (k, label) => {
    const s = sec(k);
    if (s.status === "error") return `<div class="unavail">⚠ ${esc(label)}: source unavailable right now.</div>`;
    if (s.status === "stale") return `<p class="note">⚠ ${esc(label)}: source unavailable, showing data from ${esc(ago(s.stale_since || s.fetched_at) || "earlier")}.</p>`;
    if (s.status === "partial") return `<p class="note">⚠ Some ${esc(label)} sources unavailable: ${esc(s.data.errors.join(", "))}</p>`;
    return "";
  };

  function story(it, showRegion) {
    const srcs = it.sources.map((s) => `<a href="${esc(safeUrl(s.url))}" target="_blank" rel="noopener">${esc(s.name)}</a>`).join(", ");
    const tag = showRegion && it.region ? `<span class="tag r-${esc(it.region.replace(" ", "-"))}">${esc(it.region)}</span>` : "";
    const link = safeUrl(it.sources[0].url);
    return `<article class="story"><div class="meta">${tag}<span class="srcs">${srcs}</span><span>· ${esc(ago(it.time))}</span></div>
      <h4><a href="${esc(link)}" target="_blank" rel="noopener">${esc(it.title)}</a></h4>${it.summary ? `<p>${esc(it.summary)}</p>` : ""}</article>`;
  }

  function renderNews(id, key, label, opts = {}) {
    const s = sec(key);
    let html = note(key, label);
    if (s.data) {
      let items = s.data.items;
      if (opts.region && region !== "All") items = items.filter((i) => i.region === region);
      items = items.slice(0, opts.limit || DATA.news_items_shown);
      html += items.length ? items.map((i) => story(i, opts.region)).join("") : '<p class="muted">No stories for this region right now.</p>';
    }
    $(id).innerHTML = html;
  }

  function renderFilter() {
    $("region-filter").innerHTML = ["All", ...REGIONS].map((r) => `<button class="chip" aria-pressed="${r === region}" data-r="${r}">${r}</button>`).join("");
    $("region-filter").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => { region = b.dataset.r; renderFilter(); renderNews("world", "world", "World news", { region: true }); }));
  }

  function quote(i, extra = "") {
    const d = digits(i.value);
    return `<div class="quote ${i.stale ? "stale" : ""}"><div class="qname">${esc(i.name)}<small>${esc(extra)}${i.stale ? " · stale" : ""}</small></div>
      <div class="qval">${fmt(i.value, d)}<span class="chg ${cls(i.change_pct)}">${pct(i.change_pct)}</span></div>${spark(i.spark)}</div>`;
  }

  function renderMarkets() {
    const th = DATA.crazy_threshold_pct;
    const anyData = ["indices", "fx", "commodities"].some((k) => sec(k).data);
    let c = `<div class="card crazy"><h3 class="sub">🔥 Going crazy <span class="muted">(moves beyond ±${th}%)</span></h3>`;
    c += !anyData ? '<p class="muted">Market data unavailable.</p>'
      : DATA.crazy.length ? DATA.crazy.map((x) => `<div class="crazy-row"><div class="qname">${esc(x.name)}<small>${esc(x.kind)}</small></div><div class="qval"><span class="chg ${cls(x.change_pct)}">${x.change_pct > 0 ? "▲" : "▼"} ${pct(x.change_pct)}</span></div><span></span></div>`).join("")
      : '<p class="muted">Nothing moved more than ' + th + '% today. A quiet day.</p>';
    $("crazy").innerHTML = c + "</div>";

    const block = (title, key, rows) => `<div class="card grp"><h3 class="sub">${title}</h3>${note(key, title)}${rows || ""}</div>`;
    const items = (k) => (sec(k).data ? sec(k).data.items : []);
    const fx = items("fx").map((i) => quote(i, i.week_change_pct != null ? `vs 1 week ago: ${pct(i.week_change_pct)}` : "")).join("");
    $("markets").innerHTML =
      block("Indices", "indices", items("indices").map((i) => quote(i)).join("")) +
      block("Currencies", "fx", fx) +
      block("Commodities", "commodities", items("commodities").map((i) => quote(i, i.unit)).join("")) +
      block("Crypto", "crypto", items("crypto").map((i) => quote(i, "USD · 24h")).join(""));
  }

  const ICON = (c, day = 1) => c === 0 ? (day ? "☀️" : "🌙") : c <= 2 ? (day ? "🌤️" : "☁️") : c === 3 ? "☁️" : c <= 48 ? "🌫️" : c <= 57 ? "🌦️" : c <= 67 ? "🌧️" : c <= 77 ? "❄️" : c <= 82 ? "🌧️" : c <= 86 ? "🌨️" : "⛈️";
  const DESC = (c) => c === 0 ? "Clear" : c <= 2 ? "Mostly clear" : c === 3 ? "Overcast" : c <= 48 ? "Fog" : c <= 57 ? "Drizzle" : c <= 67 ? "Rain" : c <= 77 ? "Snow" : c <= 82 ? "Showers" : c <= 86 ? "Snow showers" : "Thunderstorm";

  function renderWeather() {
    const s = sec("weather");
    let html = note("weather", "Weather");
    if (s.data) html += s.data.items.map((c) => `<div class="card"><div class="wx-head"><span class="wx-city">${esc(c.name)}</span>
      <span class="wx-now"><span class="ico">${ICON(c.code, c.is_day)}</span>${Math.round(c.temp)}°</span></div>
      <div class="wx-sub">${DESC(c.code)} · H ${Math.round(c.high)}° / L ${Math.round(c.low)}° · 💧 ${c.rain ?? "–"}% rain</div>
      <div class="days">${c.forecast.slice(0, 5).map((d) => `<div class="day"><b>${new Date(d.date + "T12:00").toLocaleDateString("en-GB", { weekday: "short" })}</b><span class="ico">${ICON(d.code)}</span>${Math.round(d.high)}°<br><span>${Math.round(d.low)}°</span><br><span>💧${d.rain ?? "–"}%</span></div>`).join("")}</div></div>`).join("");
    $("weather").innerHTML = html;

    const n = DATA.number_of_day;
    $("notd").innerHTML = n ? `<div class="card notd"><h3 class="sub">Number of the day</h3><div class="notd-val ${cls(parseFloat(n.value))}">${esc(n.value)}</div><p>${esc(n.label)}</p></div>` : "";
  }

  function header() {
    $("greeting").textContent = DATA.greeting;
    const tz = DATA.timezone;
    $("today").textContent = new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: tz });
    const t = new Date(DATA.generated_at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: tz });
    $("updated").textContent = `Last updated ${t} (${tz.split("/").pop().replace("_", " ")} time)`;
  }

  fetch("data.json?_=" + Date.now()).then((r) => r.json()).then((d) => {
    DATA = d;
    header(); renderFilter();
    renderNews("world", "world", "World news", { region: true });
    renderMarkets();
    renderNews("central", "central_banks", "Central banks", { limit: 5 });
    renderNews("economic", "economic", "Economic news");
    renderWeather();
  }).catch(() => { $("greeting").textContent = "Couldn't load today's data."; });
})();
