/*
 * app.js — orchestration & session management.
 *
 * Participant flow
 * ───────────────
 *   intro  →  pre-survey  →  browse  →  stage (player)
 *          →  post-survey  →  done (debriefing)
 *
 * View routing: only one section is visible at a time.
 * Owns sessionId and the logEvent() helper everyone else uses.
 */

(() => {
  "use strict";

  let cfg = window.__EXPERIMENT_CONFIG__;
  const $ = (id) => document.getElementById(id);

  // --------------------------------------------------------------- session
  const Session = {
    id: null,
    async start() {
      // Pass through the ?cond= override so the server's random arm matches
      // what we asked for. The server is the source of truth for which
      // condition this session ended up on.
      const params = new URLSearchParams(window.location.search);
      const url = params.get("cond")
        ? `/api/session/start?cond=${encodeURIComponent(params.get("cond"))}`
        : "/api/session/start";
      const r = await fetch(url, { method: "POST" });
      const data = await r.json();
      this.id = data.session_id;
      // Replace the page-render cfg with the server-resolved one so the
      // player uses the final ads array for this session's arm.
      if (data.config) {
        cfg = data.config;
        window.experiment.cfg = cfg;
      }
      this.log("session_start", {
        condition:        cfg.condition_label,
        active_condition: cfg.active_condition_resolved || null,
        condition_source: cfg.active_condition_source  || null,
      });
    },
    log(kind, payload = {}) {
      if (!this.id) return;
      fetch("/api/event", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: this.id,
          kind,
          ts_client: performance.timeOrigin + performance.now(),
          payload,
        }),
        keepalive: true,
      }).catch(() => {});
    },
  };
  window.experiment = { Session, cfg };

  // --------------------------------------------------------------- routing
  const VIEWS = ["intro", "pre-survey", "browse", "stage", "post-survey", "done"];

  function show(name) {
    VIEWS.forEach((k) => {
      const el = document.getElementById(k);
      if (el) el.classList.toggle("hidden", k !== name);
    });
    const onBrowseOrPlayer = name === "browse" || name === "stage";
    $("topnav").classList.toggle("hidden", !onBrowseOrPlayer);
    $("back-to-browse").classList.toggle("hidden", name !== "stage");
  }

  // The player calls window.experiment.show("done") when the video + any
  // postroll finishes. We intercept that first call to route through the
  // post-exposure survey, then show the real debriefing screen.
  let _postSurveyShown = false;

  window.experiment.show = function showIntercepted(name) {
    if (name === "done" && !_postSurveyShown) {
      _postSurveyShown = true;
      show("post-survey");
      window.experiment.Survey.openPost(() => {
        show("done");
        maybeShowProlificLink();
      });
      return;
    }
    show(name);
  };

  // --------------------------------------------------------------- helpers
  function maybeShowProlificLink() {
    const url = cfg.prolific_completion_url;
    if (!url) return;
    const p = $("prolific-link");
    if (!p) return;
    p.style.display = "";
    p.innerHTML = `<a href="${escapeAttr(url)}" target="_blank" rel="noopener"
      style="color:var(--accent-soft);font-weight:600;">
      Click here to return to Prolific and confirm your submission</a>`;
  }

  function escapeAttr(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  // --------------------------------------------------------------- bootstrap
  $("study-title").textContent = cfg.study_title || "AVOD-Lab";
  $("intro-text").textContent  = cfg.intro_text  || "";

  $("begin-btn").addEventListener("click", async () => {
    await Session.start();
    // Route to pre-survey first; Survey calls back with onComplete → browse.
    show("pre-survey");
    window.experiment.Survey.openPre(() => {
      show("browse");
      window.experiment.Browse.render();
      Session.log("browse_open", {});
    });
  });

  $("back-to-browse").addEventListener("click", () => {
    window.experiment.Player.teardown("back_button");
    show("browse");
    Session.log("back_to_browse", {});
  });

  $("done-back").addEventListener("click", () => {
    _postSurveyShown = false; // allow post-survey again for a second watch
    show("browse");
    Session.log("done_back_to_browse", {});
  });

  window.addEventListener("beforeunload", () => {
    Session.log("page_unload", {});
  });
})();
