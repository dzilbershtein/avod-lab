/*
 * browse.js — Netflix-style hero + horizontal carousels.
 * Reads window.experiment.cfg.catalog and renders it.
 * Tile click -> hands off to window.experiment.Player.openTitle(titleId).
 */

(() => {
  "use strict";

  const Browse = {
    rendered: false,
    render() {
      if (this.rendered) return; // catalogue is static within a session
      const { cfg, Session } = window.experiment;
      const cat = cfg.catalog;
      renderHero(cat);
      renderRows(cat);
      attachHoverLogging(Session);
      this.rendered = true;
    },
  };
  window.experiment.Browse = Browse;

  // ---------- hero -----------------------------------------------------------
  function renderHero(cat) {
    const t = cat.titles[cat.hero];
    if (!t) return;
    const hero = document.getElementById("hero");
    hero.style.background = bg(t);
    hero.innerHTML = `
      <div class="hero-shade"></div>
      <div class="hero-inner">
        <div class="hero-meta">${t.genre} · ${t.year}</div>
        <h2 class="hero-title">${escapeHtml(t.title)}</h2>
        <p class="hero-tagline">${escapeHtml(t.tagline || "")}</p>
        <button class="hero-play" data-id="${t.id}">&#9658; Play</button>
      </div>`;
    hero.querySelector(".hero-play").addEventListener("click", () => {
      window.experiment.Session.log("tile_click", {
        title_id: t.id,
        carousel: "hero",
        position: 0,
      });
      window.experiment.Player.openTitle(t.id);
    });
  }

  // ---------- carousels ------------------------------------------------------
  function renderRows(cat) {
    const root = document.getElementById("rows");
    root.innerHTML = "";
    cat.rows.forEach((row) => {
      const section = document.createElement("section");
      section.className = "row";
      section.innerHTML = `
        <h3 class="row-title">${escapeHtml(row.name)}</h3>
        <div class="row-scroll">
          <button class="row-nav row-nav--left" type="button" aria-label="Scroll left">&#10094;</button>
          <div class="row-track" data-row="${escapeAttr(row.name)}"></div>
          <button class="row-nav row-nav--right" type="button" aria-label="Scroll right">&#10095;</button>
        </div>`;
      const track = section.querySelector(".row-track");
      row.title_ids.forEach((tid, idx) => {
        const t = cat.titles[tid];
        if (!t) return;
        track.appendChild(makeTile(t, row.name, idx));
      });
      const scrollBy = () => Math.max(track.clientWidth * 0.8, 240);
      section
        .querySelector(".row-nav--left")
        .addEventListener("click", () => {
          track.scrollBy({ left: -scrollBy(), behavior: "smooth" });
          window.experiment.Session.log("carousel_scroll", {
            carousel: row.name,
            direction: "left",
          });
        });
      section
        .querySelector(".row-nav--right")
        .addEventListener("click", () => {
          track.scrollBy({ left: scrollBy(), behavior: "smooth" });
          window.experiment.Session.log("carousel_scroll", {
            carousel: row.name,
            direction: "right",
          });
        });
      root.appendChild(section);
    });
  }

  function makeTile(t, rowName, position) {
    const tile = document.createElement("button");
    tile.type = "button";
    tile.className = "tile";
    tile.dataset.titleId = t.id;
    tile.dataset.rowName = rowName;
    tile.dataset.position = String(position);
    tile.style.background = bg(t);
    tile.innerHTML = `
      <img class="tile-poster" alt="" loading="lazy"
           onerror="this.style.display='none'"
           src="${escapeAttr(t.poster || "")}">
      <div class="tile-overlay">
        <div class="tile-title">${escapeHtml(t.title)}</div>
        <div class="tile-meta">${t.genre} · ${formatDuration(t.duration_sec)}</div>
      </div>`;
    tile.addEventListener("click", () => {
      window.experiment.Session.log("tile_click", {
        title_id: t.id,
        carousel: rowName,
        position,
      });
      window.experiment.Player.openTitle(t.id);
    });
    return tile;
  }

  // ---------- hover logging (debounced) --------------------------------------
  let hoverTimer = null;
  function attachHoverLogging(Session) {
    document.getElementById("rows").addEventListener("mouseover", (e) => {
      const tile = e.target.closest(".tile");
      if (!tile) return;
      clearTimeout(hoverTimer);
      hoverTimer = setTimeout(() => {
        Session.log("tile_hover", {
          title_id: tile.dataset.titleId,
          carousel: tile.dataset.rowName,
          position: Number(tile.dataset.position),
        });
      }, 500);
    });
    document.getElementById("rows").addEventListener("mouseout", () => {
      clearTimeout(hoverTimer);
    });
  }

  // ---------- helpers --------------------------------------------------------
  function bg(t) {
    return `linear-gradient(135deg, ${t.color || "#333"} 0%, #111 100%)`;
  }
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }
  function escapeAttr(s) {
    return escapeHtml(s);
  }
  function formatDuration(s) {
    if (!s) return "";
    const m = Math.round(s / 60);
    return m < 1 ? `${s}s` : `${m} min`;
  }
})();
