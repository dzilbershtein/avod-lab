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
      // condition this session ended up on. ?test=1 tags the session as
      // test data so it's excluded from balance counts and CSV exports.
      const params = new URLSearchParams(window.location.search);
      const qs = new URLSearchParams();
      if (params.get("cond")) qs.set("cond", params.get("cond"));
      if (params.get("test"))  qs.set("test", params.get("test"));
      const url = qs.toString() ? `/api/session/start?${qs.toString()}` : "/api/session/start";
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
    // allow_return_to_catalogue (experiment.json) decides whether a viewer may
    // leave a video for the catalogue before its ad starts; when false, opening
    // a video is final and no back button is shown.
    $("back-to-browse").classList.toggle("hidden", name !== "stage" || !cfg.allow_return_to_catalogue);
    $("no-return-note").hidden = !!cfg.allow_return_to_catalogue;
    window.scrollTo(0, 0); // each view starts at the top, not where the last one was scrolled
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
    p.innerHTML = `<strong>Last step:</strong> <a href="${escapeAttr(url)}" rel="noopener"
      style="color:var(--accent-soft);font-weight:600;">
      click here to return to Prolific and confirm your submission</a>.`;
    const note = $("close-tab-note");
    if (note) note.style.display = "none";
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
    const Player = window.experiment.Player;
    if (Player && !Player.canLeave()) {
      // An ad has already started — participant must complete this title.
      const msg = document.getElementById("player-status") ||
        (() => { const d = document.createElement("div"); d.id = "player-status"; document.getElementById("player-wrap").appendChild(d); return d; })();
      msg.dataset.kind = "info";
      msg.textContent = "Please complete this video and the short survey first — the catalogue will be available again after.";
      msg.classList.remove("hidden");
      setTimeout(() => msg.classList.add("hidden"), 4000);
      Session.log("back_blocked", { reason: "ad_in_progress" });
      return;
    }
    Player.teardown("back_button");
    show("browse");
    Session.log("back_to_browse", {});
  });

  $("submit-comment").addEventListener("click", () => {
    const text = ($("debrief-comment").value || "").trim();
    if (!text) return;
    Session.log("debrief_comment", { text });
    $("debrief-comment").readOnly = true;
    $("submit-comment").disabled = true;
    const sent = $("comment-sent");
    if (sent) sent.style.display = "inline";
  });

  window.addEventListener("beforeunload", () => {
    Session.log("page_unload", {});
  });
})();
