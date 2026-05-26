/*
 * player.js — playback + ad scheduling + banner.
 * Exposes window.experiment.Player.openTitle(titleId) and teardown(reason).
 *
 * Robustness notes:
 *  - Both the main video and the ad video have a URL fallback chain
 *    (primary + fallback_urls).  An error event walks the chain.
 *  - Visible on-player errors surface when a URL fails so the experimenter
 *    can see what went wrong without opening devtools.
 *  - Autoplay: the click on a tile counts as a user gesture; we still mute
 *    the ad video as a belt-and-braces measure and unmute on first frame
 *    (no audible artefact, just guarantees play() resolves).
 */

(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);

  // DOM
  const content = $("content");
  const adVideo = $("ad-video");
  const adOverlay = $("ad-overlay");
  const adControls = $("ad-controls");
  const adCountdown = $("ad-countdown");
  const adSkipBtn = $("ad-skip");
  const banner = $("banner");
  const playPauseBtn = $("play-pause");
  const timeReadout = $("time-readout");
  const nowWatching = $("now-watching");
  const adPrompt = $("ad-prompt"); // user_initiated CTA — may be absent in legacy templates

  // Lazy-created status banner so the participant sees real errors instead
  // of a black box.
  let statusEl = null;
  function setStatus(msg, kind /* 'info' | 'error' | null */) {
    if (!statusEl) {
      statusEl = document.createElement("div");
      statusEl.id = "player-status";
      content.parentElement.appendChild(statusEl);
    }
    if (!msg) {
      statusEl.classList.add("hidden");
      statusEl.textContent = "";
      return;
    }
    statusEl.classList.remove("hidden");
    statusEl.dataset.kind = kind || "info";
    statusEl.textContent = msg;
  }

  // state
  let queue = [];          // midroll + overlay; start_at_sec resolved on loadedmetadata
  let preroll = null;
  let postroll = null;     // A0 control: plays after content ends, before "done" view
  let userInitiated = null; // A4: clickable prompt; ad plays only on click
  let userInitiatedFired = false;
  let userInitiatedPromptShown = false;   // true once prompt is actually visible
  let userInitiatedPromptStartSec = null; // resolved from prompt_start_at_frac
  let currentAd = null;
  let adDurationCap = null; // duration_target_sec for the currently playing ad
  let bannerTimers = [];
  let adCountdownInterval = null;
  let listenersAttached = false;
  let activeTitle = null;

  const Player = {
    openTitle(titleId) {
      const { cfg, Session, show } = window.experiment;
      const title = cfg.catalog.titles[titleId];
      if (!title) return;
      activeTitle = title;
      Session.log("watch_start", { title_id: title.id });
      nowWatching.innerHTML = `
        <span class="now-watching-label">Now watching</span>
        <strong>${title.title}</strong>
        <span class="now-watching-meta">${title.genre} · ${title.year}</span>`;
      show("stage");
      setStatus(null);
      setupContent(title);
      if (preroll) playAd(preroll);
      else playContent();
    },

    teardown(reason) {
      const { Session } = window.experiment;
      if (activeTitle) {
        Session.log("watch_end", {
          title_id: activeTitle.id,
          t_content: content.currentTime,
          reason: reason || "manual",
        });
      }
      // A4/B-series: if the prompt was shown but the viewer never clicked, log a decline.
      // This flags participants for the exclusion criteria in the pre-registered protocol.
      if (userInitiated && userInitiatedPromptShown && !userInitiatedFired) {
        Session.log("ad_prompt_declined", {
          ad_id: userInitiated.id || null,
          title_id: activeTitle ? activeTitle.id : null,
          t_content: content.currentTime,
          reason: reason || "manual",
        });
      }
      hardStopAd();
      hideUserInitiatedPrompt();
      content.pause();
      content.removeAttribute("src");
      content.load();
      setStatus(null);
      queue = [];
      preroll = null;
      postroll = null;
      userInitiated = null;
      userInitiatedFired = false;
      userInitiatedPromptShown = false;
      userInitiatedPromptStartSec = null;
      activeTitle = null;
    },
  };
  window.experiment.Player = Player;

  // ---------------------------------------------------------------- content
  function setupContent(title) {
    const { cfg, Session } = window.experiment;

    // Build the URL chain: primary + fallbacks.
    content._urlChain = [title.video_url, ...(title.fallback_urls || [])].filter(Boolean);
    content._urlIndex = 0;
    loadCurrentContentUrl();
    content.classList.remove("hidden");

    // Bucket placements into their respective trigger paths.
    const ads = cfg.ads || [];
    preroll = ads.find((a) => a.placement === "preroll") || null;
    postroll = ads.find((a) => a.placement === "postroll") || null;
    userInitiated = ads.find((a) => a.placement === "user_initiated") || null;
    userInitiatedFired = false;
    queue = ads
      .filter((a) => a.placement === "midroll" || a.placement === "overlay")
      .map((a) => ({ ...a, fired: false }));
    resolveQueueTimings(); // best-effort before metadata — re-runs after.
    setupUserInitiatedPrompt(userInitiated);

    if (listenersAttached) return;
    listenersAttached = true;

    // Fallback handler on the *main* content video.
    content.addEventListener("error", () => {
      const idx = content._urlIndex || 0;
      const chain = content._urlChain || [];
      const failedUrl = chain[idx];
      Session.log("video_source_error", {
        title_id: titleId(),
        url: failedUrl,
        error_code: content.error ? content.error.code : null,
      });
      if (idx + 1 < chain.length) {
        content._urlIndex = idx + 1;
        Session.log("video_source_fallback", {
          title_id: titleId(),
          from: failedUrl,
          to: chain[idx + 1],
        });
        setStatus(`Could not load ${shortUrl(failedUrl)} — trying fallback…`, "info");
        loadCurrentContentUrl();
        content.play().catch(() => {});
      } else {
        setStatus(
          `Could not load video. Last URL: ${shortUrl(failedUrl)}. ` +
          `Try a different title from the catalogue.`,
          "error"
        );
      }
    });

    // Fallback handler on the *ad* video — same shape, distinct chain.
    adVideo.addEventListener("error", onAdError);

    content.addEventListener("play", () =>
      Session.log("content_play", { title_id: titleId(), t: content.currentTime })
    );
    content.addEventListener("pause", () =>
      Session.log("content_pause", { title_id: titleId(), t: content.currentTime })
    );
    content.addEventListener("seeked", () =>
      Session.log("content_seek", { title_id: titleId(), t: content.currentTime })
    );
    content.addEventListener("ended", () => {
      Session.log("content_ended", { title_id: titleId(), t: content.currentTime });
      // A0 post-roll: play the ad before showing the done view.
      if (postroll) {
        const ad = postroll;
        postroll = null; // fire-once
        playAd(ad);
      } else {
        Player.teardown("content_ended");
        window.experiment.show("done");
      }
    });
    content.addEventListener("timeupdate", onContentTimeUpdate);
    content.addEventListener("loadedmetadata", () => {
      updateReadout();
      setStatus(null);
      resolveQueueTimings();
      resolveUserInitiatedTiming(userInitiated);
    });
    content.addEventListener("loadstart", () =>
      setStatus(`Loading ${shortUrl(content.currentSrc || content.src)}…`, "info")
    );
    content.addEventListener("canplay", () => setStatus(null));

    playPauseBtn.addEventListener("click", () => {
      if (content.paused) playContent();
      else content.pause();
    });
    content.addEventListener("play", () => (playPauseBtn.textContent = "Pause"));
    content.addEventListener("pause", () => (playPauseBtn.textContent = "Play"));
  }

  function titleId() {
    return activeTitle ? activeTitle.id : null;
  }

  function loadCurrentContentUrl() {
    const chain = content._urlChain || [];
    const idx = content._urlIndex || 0;
    if (chain[idx]) {
      content.src = chain[idx];
      content.load();
    }
  }

  function playContent() {
    const p = content.play();
    if (p && typeof p.catch === "function") {
      p.catch((err) => {
        window.experiment.Session.log("content_play_blocked", { reason: String(err) });
        setStatus(
          "Browser blocked autoplay. Click the Play button to start.",
          "info"
        );
      });
    }
  }

  function updateReadout() {
    timeReadout.textContent = `${formatTime(content.currentTime)} / ${formatTime(content.duration)}`;
  }

  function formatTime(s) {
    if (!isFinite(s)) return "0:00";
    const m = Math.floor(s / 60);
    const r = Math.floor(s % 60).toString().padStart(2, "0");
    return `${m}:${r}`;
  }

  function shortUrl(u) {
    if (!u) return "";
    try {
      const p = new URL(u, location.href);
      const path = p.pathname.length > 30 ? "…" + p.pathname.slice(-28) : p.pathname;
      return p.host + path;
    } catch (_) {
      return u.length > 50 ? u.slice(0, 50) + "…" : u;
    }
  }

  function onContentTimeUpdate() {
    updateReadout();
    if (currentAd) return;
    const t = content.currentTime;
    for (const ad of queue) {
      if (!ad.fired && ad.start_at_sec != null && t >= ad.start_at_sec) {
        ad.fired = true;
        playAd(ad);
        break;
      }
    }
    // Show the user-initiated prompt at the configured start time.
    if (userInitiated && !userInitiatedFired && !userInitiatedPromptShown &&
        userInitiatedPromptStartSec != null && t >= userInitiatedPromptStartSec) {
      userInitiatedPromptShown = true;
      if (adPrompt) adPrompt.classList.remove("hidden");
      window.experiment.Session.log("ad_prompt_shown", {
        ad_id: userInitiated.id || null,
        prompt_text: adPrompt ? adPrompt.textContent : null,
        title_id: titleId(),
        t_content: t,
      });
    }
  }

  // Resolve start_at_frac + start_at_cap_sec into an absolute start_at_sec
  // once content metadata (and therefore duration) is known. Idempotent —
  // safe to call multiple times; explicit start_at_sec values are preserved.
  function resolveQueueTimings() {
    const dur = content.duration;
    if (!isFinite(dur) || dur <= 0) return;
    for (const ad of queue) {
      if (ad.start_at_sec != null) continue;
      const frac = ad.start_at_frac;
      const cap = ad.start_at_cap_sec;
      if (frac == null && cap == null) continue;
      let t = frac != null ? frac * dur : dur;
      if (cap != null) t = Math.min(t, cap);
      ad.start_at_sec = t;
    }
    queue.sort((a, b) => (a.start_at_sec ?? 0) - (b.start_at_sec ?? 0));
    if (window.experiment && window.experiment.Session) {
      window.experiment.Session.log("ad_schedule_resolved", {
        title_id: titleId(),
        duration_sec: dur,
        schedule: queue.map((a) => ({
          id: a.id || null,
          placement: a.placement,
          start_at_sec: a.start_at_sec,
        })),
      });
    }
  }

  // ------------------------------------------------------ user-initiated (A4 / Exp-2 B-series)
  function setupUserInitiatedPrompt(ad) {
    if (!adPrompt) return;
    if (!ad) {
      hideUserInitiatedPrompt();
      return;
    }
    adPrompt.textContent = ad.prompt_text || "Watch an ad";
    adPrompt.classList.add("hidden");
    adPrompt.onclick = () => {
      if (userInitiatedFired || currentAd) return;
      userInitiatedFired = true;
      hideUserInitiatedPrompt();
      window.experiment.Session.log("ad_prompt_clicked", {
        ad_id: ad.id || null,
        title_id: titleId(),
        t_content: content.currentTime,
      });
      playAd({ ...ad, placement: "midroll" });
    };
    resolveUserInitiatedTiming(ad);
    // If timing resolved to immediate (no prompt_start_at_frac configured),
    // show the button right away rather than waiting for the first timeupdate.
    if (userInitiatedPromptStartSec === 0) {
      userInitiatedPromptShown = true;
      adPrompt.classList.remove("hidden");
      window.experiment.Session.log("ad_prompt_shown", {
        ad_id: ad.id || null,
        prompt_text: adPrompt.textContent,
        title_id: titleId(),
        t_content: 0,
      });
    }
  }

  // Resolve when the user-initiated prompt should first appear.
  // Priority: explicit prompt_start_at_sec > prompt_start_at_frac × duration > 0 (immediate).
  // If the fraction is set but duration is not yet known, leaves userInitiatedPromptStartSec
  // as null so loadedmetadata can retry.
  function resolveUserInitiatedTiming(ad) {
    if (!ad) return;
    if (typeof ad.prompt_start_at_sec === "number") {
      userInitiatedPromptStartSec = ad.prompt_start_at_sec;
      return;
    }
    const frac = ad.prompt_start_at_frac;
    const dur = content.duration;
    if (typeof frac === "number") {
      if (isFinite(dur) && dur > 0) {
        userInitiatedPromptStartSec = frac * dur;
      }
      // else: duration unknown yet — stay null, resolved again on loadedmetadata
    } else {
      // No timing configured — show immediately (legacy / default behaviour).
      userInitiatedPromptStartSec = 0;
    }
  }

  function hideUserInitiatedPrompt() {
    if (!adPrompt) return;
    adPrompt.classList.add("hidden");
    adPrompt.onclick = null;
  }

  // ---------------------------------------------------------------- ads
  function playAd(ad) {
    const { Session } = window.experiment;
    currentAd = ad;
    // duration_target_sec hard-caps playback length so the protocol's
    // "30-second ad" wording is enforced regardless of asset length.
    adDurationCap =
      typeof ad.duration_target_sec === "number" ? ad.duration_target_sec : null;
    Session.log("ad_start", {
      ad_id: ad.id,
      placement: ad.placement,
      category: ad.category || null,
      source: ad.source || null,
      duration_target_sec: adDurationCap,
      title_id: titleId(),
      t_content: content.currentTime,
    });

    if (ad.placement === "overlay") {
      runOverlay(ad);
      return;
    }

    content.pause();
    content.classList.add("hidden");

    // Build an ad URL chain — primary + ad.fallback_urls if present.
    const adChain = [ad.url, ...(ad.fallback_urls || [])].filter(Boolean);
    adVideo._urlChain = adChain;
    adVideo._urlIndex = 0;
    loadCurrentAdUrl();
    adVideo.classList.remove("hidden");
    adControls.classList.remove("hidden");
    adSkipBtn.classList.add("hidden");

    // Belt-and-braces: start muted to dodge autoplay policies, unmute on
    // first frame so the participant still hears the ad audio.
    adVideo.muted = true;
    const unmuteOnFirstFrame = () => {
      adVideo.muted = false;
      adVideo.removeEventListener("playing", unmuteOnFirstFrame);
    };
    adVideo.addEventListener("playing", unmuteOnFirstFrame);

    showBannerIfConfigured(ad);

    if (typeof ad.skippable_after_sec === "number") {
      const onTime = () => {
        if (adVideo.currentTime >= ad.skippable_after_sec) {
          adSkipBtn.classList.remove("hidden");
          adVideo.removeEventListener("timeupdate", onTime);
        }
      };
      adVideo.addEventListener("timeupdate", onTime);
    }

    startAdCountdown(ad);

    adVideo.onended = () => finishAd("complete");
    adVideo.onclick = () => {
      Session.log("ad_click", {
        ad_id: ad.id,
        category: ad.category || null,
        title_id: titleId(),
        t_ad: adVideo.currentTime,
      });
      if (ad.click_url) window.open(ad.click_url, "_blank", "noopener");
    };
    adSkipBtn.onclick = () => finishAd("skipped");

    const p = adVideo.play();
    if (p && typeof p.catch === "function") {
      p.catch((err) => {
        Session.log("ad_play_blocked", { ad_id: ad.id, reason: String(err) });
        setStatus("Autoplay blocked for ad — click anywhere on the player.", "info");
      });
    }
  }

  function loadCurrentAdUrl() {
    const chain = adVideo._urlChain || [];
    const idx = adVideo._urlIndex || 0;
    if (chain[idx]) {
      adVideo.src = chain[idx];
      adVideo.load();
    }
  }

  function onAdError() {
    if (!currentAd) return;
    const { Session } = window.experiment;
    const idx = adVideo._urlIndex || 0;
    const chain = adVideo._urlChain || [];
    const failedUrl = chain[idx];
    Session.log("ad_source_error", {
      ad_id: currentAd.id,
      url: failedUrl,
      error_code: adVideo.error ? adVideo.error.code : null,
    });
    if (idx + 1 < chain.length) {
      adVideo._urlIndex = idx + 1;
      Session.log("ad_source_fallback", {
        ad_id: currentAd.id,
        from: failedUrl,
        to: chain[idx + 1],
      });
      loadCurrentAdUrl();
      adVideo.play().catch(() => {});
    } else {
      // No more fallbacks — skip the ad and return to content so the
      // experiment doesn't deadlock.
      Session.log("ad_skipped_due_to_error", { ad_id: currentAd.id });
      setStatus(`Ad asset unavailable (${shortUrl(failedUrl)}) — skipping ad.`, "error");
      finishAd("source_error");
      setTimeout(() => setStatus(null), 3500);
    }
  }

  function runOverlay(ad) {
    const { Session } = window.experiment;
    if (ad.image_url) {
      adOverlay.src = ad.image_url;
      adOverlay.onerror = () => {
        Session.log("ad_source_error", { ad_id: ad.id, url: ad.image_url, kind: "overlay_image" });
        adOverlay.classList.add("hidden");
      };
      adOverlay.classList.remove("hidden");
      adOverlay.onclick = () => {
        Session.log("ad_click", {
          ad_id: ad.id,
          category: ad.category || null,
          title_id: titleId(),
          t_content: content.currentTime,
        });
        if (ad.click_url) window.open(ad.click_url, "_blank", "noopener");
      };
    }
    showBannerIfConfigured(ad);
    setTimeout(() => finishAd("complete"), (ad.duration_sec || 10) * 1000);
  }

  function startAdCountdown(ad) {
    // Target length = duration cap if set (the protocol's 30s spec), else
    // the asset's natural duration. The cap also terminates the ad early.
    const target =
      adDurationCap != null
        ? adDurationCap
        : (ad.duration_sec || 0);
    const tick = () => {
      const remaining = Math.max(0, target - adVideo.currentTime);
      adCountdown.textContent = `Ad: ${Math.ceil(remaining)}s`;
      if (adDurationCap != null && adVideo.currentTime >= adDurationCap) {
        // Enforce the spec-mandated duration even if the asset is longer.
        finishAd("duration_cap");
      }
    };
    tick();
    adCountdownInterval = setInterval(tick, 250);
  }

  function finishAd(reason) {
    if (!currentAd) return;
    const ad = currentAd;
    window.experiment.Session.log("ad_end", {
      ad_id: ad.id,
      placement: ad.placement,
      category: ad.category || null,
      source: ad.source || null,
      duration_target_sec: adDurationCap,
      title_id: titleId(),
      reason,
      t_ad: adVideo ? adVideo.currentTime : null,
    });
    const placement = ad.placement;
    hardStopAd();
    if (placement === "preroll" || placement === "midroll") {
      content.classList.remove("hidden");
      playContent();
    } else if (placement === "postroll") {
      // A0: content already ended; ad finished — tear down and show done.
      Player.teardown("postroll_complete");
      window.experiment.show("done");
    }
  }

  function hardStopAd() {
    if (adCountdownInterval) {
      clearInterval(adCountdownInterval);
      adCountdownInterval = null;
    }
    clearBanner();
    adControls.classList.add("hidden");
    adSkipBtn.classList.add("hidden");
    adOverlay.classList.add("hidden");
    adOverlay.removeAttribute("src");
    adVideo.pause();
    adVideo.removeAttribute("src");
    adVideo.classList.add("hidden");
    currentAd = null;
    adDurationCap = null;
  }

  // ---------------------------------------------------------------- banner
  function showBannerIfConfigured(ad) {
    if (!ad.banner || !ad.banner.show) return;
    const { Session } = window.experiment;
    const showAt = ad.banner.show_at_ad_sec ?? 0;
    const hideAt = ad.banner.hide_at_ad_sec ?? ad.duration_sec ?? 10;

    bannerTimers.push(
      setTimeout(() => {
        banner.textContent = ad.banner.text || "";
        banner.classList.remove("hidden");
        Session.log("banner_shown", {
          ad_id: ad.id,
          title_id: titleId(),
          text: ad.banner.text,
        });
      }, showAt * 1000)
    );
    bannerTimers.push(
      setTimeout(() => {
        banner.classList.add("hidden");
        Session.log("banner_hidden", { ad_id: ad.id, title_id: titleId() });
      }, hideAt * 1000)
    );
    banner.onclick = () =>
      Session.log("banner_click", {
        ad_id: ad.id,
        title_id: titleId(),
        text: ad.banner.text,
      });
  }

  function clearBanner() {
    bannerTimers.forEach((id) => clearTimeout(id));
    bannerTimers = [];
    banner.classList.add("hidden");
    banner.textContent = "";
  }
})();
