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
 *   IUIPC                 : 9 items from Malhotra et al. (2004), 3 per subscale
 *   Intrusiveness         : 7 items from Li et al. (2002)
 *   Irritation            : 5 items from Edwards et al. (2002)
 *   Ad / platform attitude: 3-item semantic differentials
 *   Perceived ad-content fit : 3 items (rel_1–rel_3; H3b/H3c mediator)
 *   Skip intention           : 1 item
 *   Perceived control        : 5-point item, A3 manipulation check only
 *   Relevance manipulation check : 1 item (manip_relevance; page 5, all conditions)
 */

(() => {
  "use strict";

  // ── helpers ────────────────────────────────────────────────────────────────

  const L7  = (id, label, extra = {}) => ({ id, type: "likert7", label, ...extra });
  const L5  = (id, label)             => ({ id, type: "likert5", label });
  const RDO = (id, label, options)    => ({ id, type: "radio",   label, options });
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
        RDO("age", "Your age group",
          ["18–24", "25–34", "35–44", "45–54", "55 or older"]),
        RDO("gender", "Gender",
          ["Male", "Female", "Non-binary / third gender", "Prefer not to say"]),
        RDO("vod_freq",
          "How often do you watch ad-supported streaming video (e.g. YouTube with ads, Netflix, Prime Video, etc.)?",
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
        L7("iuipc_col_3",
          "When online companies ask me for personal information, I sometimes think twice before providing it."),
        L7("iuipc_ctl_1",
          "Online companies should be required to get my permission before using my personal information for any purpose."),
        L7("iuipc_ctl_2",
          "I want to have complete control over what online companies do with my personal information."),
        L7("iuipc_ctl_3",
          "Consumer online privacy is really a matter of consumers' right to exercise control over how their information is collected, used, and shared."),
        L7("iuipc_awa_1",
          "Online companies should clearly disclose how they use the personal information they collect from me."),
        L7("iuipc_awa_2",
          "I am usually aware of whether or not an online company is collecting information about me."),
        L7("iuipc_awa_3",
          "It is very important to me to be aware of what online companies do with my personal information."),
        ATT("attn_pre", 6),
      ],
    },
  ];

  // ── Post-survey pages (condition-aware) ─────────────────────────────────────

  function buildPostPages(condition) {
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
        id: "skip_intention",
        title: "About the ad (continued)",
        intro: "Please rate your agreement.\n(1 = Strongly disagree  ·  7 = Strongly agree)",
        items: [
          L7("rel_1", "The advertised product was relevant to the video I watched."),
          L7("rel_2", "The ad fit well with the content I chose."),
          L7("rel_3", "It made sense to show this particular ad with this video."),
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
    ];
  }

  function buildManipItems(condition) {
    const items = [];
    if (condition === "A3") {
      items.push(L5("manip_control",
        "To what extent did you feel in control of when the ad played?"));
    }
    items.push(
      RDO("manip_ad_seen",
        "Did you see an advertisement during or after the video clip?",
        ["Yes, and I watched it", "Yes, but I did not pay much attention to it", "No"]),
      RDO("manip_prior_ad",
        "Had you seen this specific advertisement before today?",
        ["Yes", "No", "Not sure"]),
      L7("manip_relevance",
        "The ad appeared to be chosen based on the type of video I watched.")
    );
    return items;
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

    return wrap;
  }

  // ── Response collection ─────────────────────────────────────────────────────

  function collectPage(container, page, responses) {
    for (const item of page.items) {
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
