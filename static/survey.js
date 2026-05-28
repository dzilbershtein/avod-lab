/*
 * survey.js — Experiment 1 pre- and post-exposure questionnaire.
 *
 * Exposes window.experiment.Survey with:
 *   .openPre(onComplete)   renders the pre-exposure battery, calls onComplete()
 *   .openPost(onComplete)  renders the post-exposure battery, calls onComplete()
 *
 * Each survey page is logged as:
 *   Session.log("survey_page", { survey, page, responses })
 * The final page logs:
 *   Session.log("survey_complete", { survey, all_responses })
 *
 * Attention-check results are included in the page payload as
 *   { attn_pre_pass: true/false, attn_post_pass: true/false }
 *
 * Scales used
 * -----------
 *   Persuasion knowledge  : 3 items adapted from Friestad & Wright (1994) /
 *                           Jung et al. (2019)
 *   IUIPC (short form)    : 6 items from Malhotra et al. (2004)
 *   Intrusiveness         : 7 items from Li et al. (2002)
 *   Irritation            : 5 items from Edwards et al. (2002)
 *   Ad / platform attitude: 3-item semantic differentials
 *   Purchase intention    : 3 items
 *   Skip intention        : 1 item
 *   Perceived control     : 5-point item, A4 manipulation check only
 */

(() => {
  "use strict";

  // ── helpers ────────────────────────────────────────────────────────────────

  const L7  = (id, label, extra = {}) => ({ id, type: "likert7", label, ...extra });
  const L5  = (id, label)             => ({ id, type: "likert5", label });
  const RDO = (id, label, options)    => ({ id, type: "radio",   label, options });
  const NUM = (id, label, min, max)   => ({ id, type: "number",  label, min, max });
  const SD  = (id, left, right, grp)  => ({ id, type: "semdiff", left, right, _group: grp || null });
  const ATT = (id, correct)           => L7(id,
    `Attention check — please select "${LABELS7[correct - 1]}" (${correct}) to confirm you are reading carefully.`,
    { _attn: true, _correct: correct });

  const LABELS7 = ["Strongly disagree","Disagree","Somewhat disagree",
                   "Neither agree nor disagree",
                   "Somewhat agree","Agree","Strongly agree"];
  const LABELS5 = ["Not at all","Slightly","Moderately","Quite a bit","Completely"];

  // ── Pre-survey pages ────────────────────────────────────────────────────────

  const PRE_PAGES = [
    {
      id: "demographics",
      title: "Background questions",
      intro: "Please answer a few short questions before you start. Your answers are kept confidential and used only for research purposes.",
      items: [
        NUM("age",    "Your age (years)", 18, 99),
        RDO("gender", "Gender",
          ["Male", "Female", "Non-binary / third gender", "Prefer not to say"]),
        RDO("vod_freq",
          "How often do you watch ad-supported streaming video (e.g. YouTube with ads, Tubi, Peacock Free, ITVX)?",
          ["Daily", "Several times a week", "Weekly", "Less than weekly",
           "Never or almost never"]),
      ],
    },
    {
      id: "persuasion_knowledge",
      title: "Your views on advertising",
      intro: "Please rate your agreement with each statement.\n(1 = Strongly disagree  ·  7 = Strongly agree)",
      items: [
        L7("pk_1", "Advertisers try to get people to buy things they don't really need."),
        L7("pk_2", "When I see an ad, I can tell it is designed to persuade me."),
        L7("pk_3", "I understand the techniques that advertisers use to influence people."),
      ],
    },
    {
      id: "privacy_concern",
      title: "Online privacy",
      intro: "Please rate your agreement with each statement.\n(1 = Strongly disagree  ·  7 = Strongly agree)",
      items: [
        L7("iuipc_col_1",
          "It bothers me to give personal information to so many online companies."),
        L7("iuipc_col_2",
          "I am concerned that online companies are collecting too much personal information about me."),
        L7("iuipc_ctl_1",
          "Online companies should be required to get my permission before using my personal information for any purpose."),
        L7("iuipc_ctl_2",
          "I want to have complete control over what online companies do with my personal information."),
        L7("iuipc_awa_1",
          "Online companies should clearly disclose how they use the personal information they collect from me."),
        L7("iuipc_awa_2",
          "I am usually aware of whether or not an online company is collecting information about me."),
        ATT("attn_pre", 6),
      ],
    },
  ];

  // ── Post-survey pages (condition-aware) ─────────────────────────────────────

  function buildPostPages(condition) {
    // Shuffle stated-preference options to avoid order effects.
    const prefOptions = shuffle([
      { id: "pref_postroll",   label: "An ad plays automatically after the video ends (no interruption to viewing)" },
      { id: "pref_preroll",    label: "An ad plays before the video starts (no skip option)" },
      { id: "pref_midroll",    label: "An ad interrupts the video at the midpoint (no skip option)" },
      { id: "pref_overlay",    label: "A banner ad appears over the video while it continues playing" },
      { id: "pref_initiated",  label: "You can choose to watch an ad at any point during the video" },
    ]);

    return [
      {
        id: "intrusiveness",
        title: "About the ad",
        intro: "Please rate your agreement with each statement about the ad you just saw.\n(1 = Strongly disagree  ·  7 = Strongly agree)",
        items: [
          L7("int_1", "The ad was intrusive."),
          L7("int_2", "The ad was forced on me."),
          L7("int_3", "The ad was invasive."),
          L7("int_4", "The ad disturbed me."),
          L7("int_5", "The ad was obtrusive."),
          L7("int_6", "The ad intruded on what I was doing."),
          L7("int_7", "The ad interrupted my activity."),
        ],
      },
      {
        id: "irritation",
        title: "About the ad (continued)",
        intro: "Please rate your agreement.\n(1 = Strongly disagree  ·  7 = Strongly agree)",
        items: [
          L7("irr_1", "I found the ad irritating."),
          L7("irr_2", "I found the ad annoying."),
          L7("irr_3", "I found the ad aggravating."),
          L7("irr_4", "I found the ad unpleasant."),
          L7("irr_5", "I was bothered by the ad."),
        ],
      },
      {
        id: "secondary_attitudes",
        title: "Your experience",
        intro: "Please answer the following questions about your experience.",
        items: [
          L7("sat_1", "Overall, I was satisfied with the viewing experience."),
          SD("ad_att_1",   "Bad",          "Good",        "My overall attitude toward the ad:"),
          SD("ad_att_2",   "Unfavourable", "Favourable",  null),
          SD("ad_att_3",   "Negative",     "Positive",    null),
          SD("plat_att_1", "Bad",          "Good",        "My overall attitude toward this platform:"),
          SD("plat_att_2", "Unfavourable", "Favourable",  null),
          SD("plat_att_3", "Untrustworthy","Trustworthy", null),
        ],
      },
      {
        id: "purchase_skip",
        title: "About the product",
        intro: "Please rate your agreement.\n(1 = Strongly disagree  ·  7 = Strongly agree)",
        items: [
          L7("pi_1",   "I would consider purchasing the product advertised."),
          L7("pi_2",   "I am interested in the product advertised."),
          L7("pi_3",   "It is likely that I would buy the product advertised."),
          L7("skip_1", "If I could have skipped this ad, I would have."),
          ATT("attn_post", 5),
        ],
      },
      {
        id: "manip_checks",
        title: "A few more questions",
        intro: null,
        items: buildManipItems(condition),
      },
      {
        id: "preferences",
        title: "Ad format preferences",
        intro: "Different streaming services use different ad formats. Please rank the five formats below from most preferred (1 = most preferred) to least preferred (5 = least preferred) by using the ▲ ▼ buttons.",
        items: [
          { id: "pref_rank", type: "ranking", options: prefOptions },
        ],
      },
    ];
  }

  function buildManipItems(condition) {
    const items = [];
    if (condition === "A3") {
      items.push(RDO("manip_overlay_noticed",
        "During the video, did you notice any image or banner displayed on top of the video while it was playing?",
        ["Yes", "No", "I am not sure"]));
    }
    if (condition === "A4") {
      items.push(L5("manip_control",
        "To what extent did you feel in control of when you watched the ad?"));
    }
    items.push(
      RDO("manip_ad_seen",
        "Did you see an advertisement during or after the video clip?",
        ["Yes, and I watched it", "Yes, but I did not pay much attention to it", "No"]),
      RDO("manip_prior_ad",
        "Had you seen this specific advertisement before today?",
        ["Yes", "No", "Not sure"])
    );
    return items;
  }

  function shuffle(arr) {
    const a = arr.slice();
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  }

  // ── Renderer ────────────────────────────────────────────────────────────────

  function renderPage(container, page, responses) {
    container.innerHTML = "";

    const h2 = el("h2", "survey-title", page.title);
    container.appendChild(h2);

    if (page.intro) {
      const p = el("p", "survey-intro");
      p.textContent = page.intro;
      container.appendChild(p);
    }

    for (const item of page.items) {
      if (item._group) {
        container.appendChild(el("p", "survey-group-label", item._group));
      }
      container.appendChild(renderItem(item, responses));
    }
  }

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls)  e.className = cls;
    if (text) e.textContent = text;
    return e;
  }

  function renderItem(item, responses) {
    const wrap = el("div", "survey-item");
    wrap.dataset.id = item.id;

    if (item.type === "likert7" || item.type === "likert5") {
      const labels = item.type === "likert7" ? LABELS7 : LABELS5;
      const n = labels.length;
      const lbl = el("p", "survey-item-label" + (item._attn ? " attn-check" : ""), item.label);
      wrap.appendChild(lbl);

      const row = el("div", "likert-radios");
      row.dataset.n = n;
      for (let v = 1; v <= n; v++) {
        const cell = el("label", "likert-cell");
        const inp  = document.createElement("input");
        inp.type  = "radio";
        inp.name  = item.id;
        inp.value = v;
        if (responses[item.id] === v) inp.checked = true;
        cell.appendChild(inp);
        cell.appendChild(el("span", "likert-val", String(v)));
        row.appendChild(cell);
      }

      const anchors = el("div", "likert-anchors");
      anchors.appendChild(el("span", null, labels[0]));
      anchors.appendChild(el("span", null, labels[n - 1]));

      wrap.appendChild(row);
      wrap.appendChild(anchors);
      return wrap;
    }

    if (item.type === "semdiff") {
      const row = el("div", "semdiff-row");
      row.appendChild(el("span", "semdiff-pole semdiff-left", item.left));
      const radios = el("div", "semdiff-radios");
      for (let v = 1; v <= 7; v++) {
        const cell = el("label", "semdiff-cell");
        const inp  = document.createElement("input");
        inp.type  = "radio";
        inp.name  = item.id;
        inp.value = v;
        if (responses[item.id] === v) inp.checked = true;
        cell.appendChild(inp);
        cell.appendChild(el("span", "semdiff-val", String(v)));
        radios.appendChild(cell);
      }
      row.appendChild(radios);
      row.appendChild(el("span", "semdiff-pole semdiff-right", item.right));
      wrap.appendChild(row);
      return wrap;
    }

    if (item.type === "radio") {
      wrap.appendChild(el("p", "survey-item-label", item.label));
      const opts = el("div", "radio-options");
      for (const opt of item.options) {
        const lbl  = el("label", "radio-option");
        const inp  = document.createElement("input");
        inp.type  = "radio";
        inp.name  = item.id;
        inp.value = opt;
        if (responses[item.id] === opt) inp.checked = true;
        lbl.appendChild(inp);
        lbl.appendChild(el("span", null, opt));
        opts.appendChild(lbl);
      }
      wrap.appendChild(opts);
      return wrap;
    }

    if (item.type === "number") {
      const lbl = el("label", "survey-item-label", item.label);
      lbl.htmlFor = item.id;
      const inp = document.createElement("input");
      inp.type    = "number";
      inp.id      = item.id;
      inp.name    = item.id;
      inp.min     = item.min;
      inp.max     = item.max;
      inp.className = "number-input";
      if (responses[item.id] != null) inp.value = responses[item.id];
      wrap.appendChild(lbl);
      wrap.appendChild(inp);
      return wrap;
    }

    if (item.type === "ranking") {
      // Ordered list of options — the viewer reorders using ▲▼ buttons.
      // responses[item.id] is stored as an array of option IDs in ranked order.
      const ordered = responses[item.id]
        ? item.options.slice().sort(
            (a, b) => responses[item.id].indexOf(a.id) - responses[item.id].indexOf(b.id))
        : item.options.slice();
      if (!responses[item.id]) responses[item.id] = ordered.map(o => o.id);

      const list = el("div", "rank-list");
      function redrawList() {
        list.innerHTML = "";
        ordered.forEach((opt, idx) => {
          const row    = el("div", "rank-row");
          const badge  = el("span", "rank-badge", String(idx + 1));
          const label  = el("span", "rank-label", opt.label);
          const btnUp  = el("button", "rank-btn");
          const btnDn  = el("button", "rank-btn");
          btnUp.type = btnDn.type = "button";
          btnUp.textContent = "▲";
          btnDn.textContent = "▼";
          btnUp.disabled = idx === 0;
          btnDn.disabled = idx === ordered.length - 1;
          btnUp.onclick = () => {
            ordered.splice(idx - 1, 0, ordered.splice(idx, 1)[0]);
            responses[item.id] = ordered.map(o => o.id);
            redrawList();
          };
          btnDn.onclick = () => {
            ordered.splice(idx + 1, 0, ordered.splice(idx, 1)[0]);
            responses[item.id] = ordered.map(o => o.id);
            redrawList();
          };
          row.append(badge, label, btnUp, btnDn);
          list.appendChild(row);
        });
      }
      redrawList();
      wrap.appendChild(list);
      return wrap;
    }

    return wrap;
  }

  // ── Response collection ─────────────────────────────────────────────────────

  function collectPage(container, page, responses) {
    for (const item of page.items) {
      if (item.type === "ranking") continue; // maintained by onclick handlers
      if (item.type === "number") {
        const inp = container.querySelector(`#${item.id}`);
        if (inp && inp.value !== "") responses[item.id] = parseInt(inp.value, 10);
        continue;
      }
      const checked = container.querySelector(`input[name="${item.id}"]:checked`);
      if (checked) {
        responses[item.id] = (item.type === "semdiff" ||
                              item.type === "likert7"  ||
                              item.type === "likert5")
          ? parseInt(checked.value, 10) : checked.value;
      }
    }
  }

  function validatePage(container, page, responses) {
    const missing = [];
    for (const item of page.items) {
      if (item.type === "ranking") continue;
      if (responses[item.id] == null) {
        missing.push(item.id);
        container.querySelector(`.survey-item[data-id="${item.id}"]`)
          ?.classList.add("missing");
      } else {
        container.querySelector(`.survey-item[data-id="${item.id}"]`)
          ?.classList.remove("missing");
      }
    }
    return missing;
  }

  // ── Survey runner ───────────────────────────────────────────────────────────

  function runSurvey({ bodyEl, backBtn, nextBtn, progressEl, pages, surveyId, onComplete }) {
    let pageIdx = 0;
    const responses = {};

    function goTo(idx) {
      pageIdx = idx;
      renderPage(bodyEl, pages[idx], responses);
      window.scrollTo(0, 0);
      backBtn.classList.toggle("hidden", idx === 0);
      nextBtn.textContent = idx < pages.length - 1 ? "Next →" : "Submit";
      if (progressEl) progressEl.textContent = `${idx + 1} / ${pages.length}`;
    }

    backBtn.onclick = () => {
      collectPage(bodyEl, pages[pageIdx], responses);
      goTo(pageIdx - 1);
    };

    nextBtn.onclick = () => {
      collectPage(bodyEl, pages[pageIdx], responses);
      const missing = validatePage(bodyEl, pages[pageIdx], responses);
      if (missing.length) {
        let errEl = bodyEl.querySelector(".survey-error");
        if (!errEl) {
          errEl = el("p", "survey-error", "Please answer all questions before continuing.");
          bodyEl.prepend(errEl);
        } else {
          errEl.textContent = "Please answer all questions before continuing.";
        }
        window.scrollTo(0, 0);
        return;
      }

      const page = pages[pageIdx];
      const payload = { survey: surveyId, page: page.id, responses: {} };
      for (const item of page.items) {
        if (responses[item.id] != null) {
          payload.responses[item.id] = responses[item.id];
          if (item._attn)
            payload.responses[`${item.id}_pass`] = (responses[item.id] === item._correct);
        }
      }
      window.experiment.Session.log("survey_page", payload);

      if (pageIdx < pages.length - 1) {
        goTo(pageIdx + 1);
      } else {
        window.experiment.Session.log("survey_complete",
          { survey: surveyId, all_responses: responses });
        onComplete(responses);
      }
    };

    goTo(0);
  }

  // ── Public API ──────────────────────────────────────────────────────────────

  const Survey = {
    openPre(onComplete) {
      runSurvey({
        bodyEl:     document.getElementById("pre-survey-body"),
        backBtn:    document.getElementById("pre-back"),
        nextBtn:    document.getElementById("pre-next"),
        progressEl: document.getElementById("pre-progress"),
        pages:      PRE_PAGES,
        surveyId:   "pre",
        onComplete,
      });
    },
    openPost(onComplete) {
      const cond = (window.experiment.cfg || {}).active_condition_resolved || null;
      runSurvey({
        bodyEl:     document.getElementById("post-survey-body"),
        backBtn:    document.getElementById("post-back"),
        nextBtn:    document.getElementById("post-next"),
        progressEl: document.getElementById("post-progress"),
        pages:      buildPostPages(cond),
        surveyId:   "post",
        onComplete,
      });
    },
  };

  window.experiment = window.experiment || {};
  window.experiment.Survey = Survey;
})();
