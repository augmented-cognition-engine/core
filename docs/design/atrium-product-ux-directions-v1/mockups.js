const fixture = {
  brief: 'AI Command Brief — capability up, unit cost down',
  summary: 'The market is separating model capability from model economics. Buyers can now demand both stronger reasoning and lower unit cost.',
  shift: 'Frontier inference costs moved down again',
  changed: 'Published token prices fell while long-context tiers expanded across two providers.',
  matters: 'Capability and unit cost are moving independently, changing enterprise build-versus-buy assumptions.',
  signal: 'Three provider price changes entered the current watch window.',
  caseTitle: 'Enterprise AI economics opportunity',
  caseBody: 'Revisit build-versus-buy assumptions using current unit economics.',
  source: 'Model provider release feeds',
  sourceDetail: 'Official model cards, release notes, and provider announcements.',
};

const icons = {
  mark: `<svg viewBox="0 0 34 34" aria-hidden="true"><path d="M17 3 29 10v14L17 31 5 24V10Z" fill="none" stroke="currentColor"/><path d="m10 18 4-7 4 12 6-9" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  search: `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6"/><path d="m16 16 4 4"/></svg>`,
  arrow: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14m-5-5 5 5-5 5"/></svg>`,
  chevron: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m8 10 4 4 4-4"/></svg>`,
};

function shell(direction, active, body, aside = '') {
  const label = direction === 'a' ? 'Living Brief' : direction === 'b' ? 'Evidence Ledger' : 'Command Atlas';
  return `
    <div class="product theme-${direction}">
      <aside class="nav">
        <div class="brand">${icons.mark}<span>ACE</span></div>
        <button class="domain"><span><small>Domain</small>World Intelligence</span>${icons.chevron}</button>
        <nav aria-label="Domain surfaces">
          ${['Overview','Explore','Build','Operate','Consumers'].map(item => `<a class="${active === item ? 'active' : ''}" href="#">${item}</a>`).join('')}
        </nav>
        <div class="global"><small>GLOBAL</small><a>Domain Packs</a><a>Connections</a><a>Workspace</a></div>
        <div class="nav-foot"><span class="health-dot"></span><span>Maintaining</span><button aria-label="Open settings">•••</button></div>
      </aside>
      <section class="workspace">
        <header class="topbar">
          <div class="mobile-brand">${icons.mark}<strong>ACE</strong></div>
          <span class="crumb">World Intelligence <b>/</b> ${active}</span>
          <label class="command">${icons.search}<input aria-label="Ask or search" value="" placeholder="Ask ACE or search the domain" /></label>
          <button class="icon-button" aria-label="Open activity">⌁</button>
        </header>
        ${body}
      </section>
      ${aside}
      <span class="direction-label">${label} · fixture-backed concept</span>
    </div>`;
}

function healthA() {
  return `<section class="health-band" aria-label="Domain Health">
    <div><span class="health-dot"></span><p><small>DOMAIN HEALTH</small><strong>Maintained with limits</strong></p></div>
    <dl><div><dt>Coverage</dt><dd>Partial · 1 admitted role</dd></div><div><dt>Freshness</dt><dd>Current watch window</dd></div><div><dt>Confidence</dt><dd>Not scored</dd></div><div><dt>Conflicts</dt><dd>None admitted</dd></div></dl>
    <button>All 8 dimensions ${icons.arrow}</button>
  </section>`;
}

function whyPanel(direction) {
  return `<aside class="why-panel theme-${direction}" aria-label="Why this assessment">
    <header><div><small>WHY THIS ASSESSMENT</small><h2>${fixture.shift}</h2></div><button aria-label="Close">×</button></header>
    <p class="why-summary">${fixture.matters}</p>
    <ol class="derivation">
      <li><span>01</span><div><small>OBSERVATION</small><p>${fixture.changed}</p></div></li>
      <li><span>02</span><div><small>RESOLVED ENTITIES</small><p>Two provider release records · pricing and long-context tiers</p></div></li>
      <li><span>03</span><div><small>MATERIAL EVENT</small><p>${fixture.shift}</p></div></li>
      <li><span>04</span><div><small>SIGNAL</small><p>${fixture.signal}</p></div></li>
      <li><span>05</span><div><small>ASSESSMENT</small><p>${fixture.caseBody}</p></div></li>
    </ol>
    <section class="evidence-box"><small>SUPPORTING EVIDENCE</small><strong>${fixture.source}</strong><p>${fixture.sourceDetail}</p><span>1 cited record · current watch window</span></section>
    <section class="unknown-box"><small>LIMIT</small><p>Confidence is not numerically scored by the current fixture contract. No conflict record is admitted.</p></section>
    <footer><button>Open operator lineage</button><span>Raw receipts stay in Operate</span></footer>
  </aside>`;
}

function overviewA() {
  const body = `<div class="overview living">
    <section class="lead">
      <div class="eyebrow"><span>BRIEF · CURRENT</span><span>Recalculated in current watch window</span></div>
      <h1>${fixture.brief}</h1>
      <p class="lead-copy">${fixture.summary}</p>
      <div class="lead-actions"><button class="primary">Read the current state ${icons.arrow}</button><button class="text-button">Why this conclusion?</button></div>
      <div class="weave" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div>
    </section>
    ${healthA()}
    <section class="ranked">
      <div class="section-title"><p><small>SINCE YOUR LAST VISIT</small><strong>One material movement changes the picture.</strong></p><button>View timeline</button></div>
      <article class="movement"><span class="rank">01</span><div><small>SHIFT · SUPPORTED</small><h2>${fixture.shift}</h2><p>${fixture.changed}</p></div><div class="implication"><small>IMPLICATION</small><p>${fixture.matters}</p><button>Open Why? ${icons.arrow}</button></div></article>
      <div class="lower-grid"><article><small>SIGNAL · WATCHING</small><h3>Provider pricing signal</h3><p>${fixture.signal}</p><span>Evidence role: first-party claim</span></article><article><small>UNKNOWN · NEEDS EVIDENCE</small><h3>Independent reliability</h3><p>No independent reliability source is admitted in this fixture.</p><button>Review source gap</button></article><article><small>ATTENTION · DECISION OPENING</small><h3>${fixture.caseTitle}</h3><p>${fixture.caseBody}</p><button>Inspect opening</button></article></div>
    </section>
  </div>`;
  return shell('a', 'Overview', body);
}

function exploreA() {
  const body = `<div class="explore living">
    <header class="explore-head"><small>EXPLORE THE WORLD</small><h1>What changed in token economics?</h1><div class="query">${icons.search}<span>${fixture.changed}</span><button>Ask</button></div></header>
    <div class="explore-layout"><section class="answer-column"><div class="answer-meta"><span>SUPPORTED ANSWER</span><span>1 cited record · 1 linked Shift</span></div><h2>${fixture.shift}</h2><p class="answer-copy">${fixture.changed} ${fixture.matters}</p><button class="primary">Open Why? ${icons.arrow}</button><div class="context-line"><span>Brief</span><i></i><span>Shift</span><i></i><span>Source</span></div>
      <article class="entity-focus"><header><div><small>FOCUSED ENTITY SET</small><h3>Provider releases · current window</h3></div><select aria-label="Relationship depth"><option>Depth 1</option></select></header><div class="mini-graph"><span class="node root">Token economics</span><span class="line l1"></span><span class="node n1">Pricing</span><span class="line l2"></span><span class="node n2">Context tiers</span><span class="line l3"></span><span class="node n3">Provider releases</span></div><footer><button>Timeline</button><span>Only relationships supporting this answer are shown.</span></footer></article>
    </section><aside class="basis"><small>EVIDENCE BASIS</small><article><span>01</span><h3>${fixture.source}</h3><p>${fixture.sourceDetail}</p><dl><div><dt>Role</dt><dd>First-party claim</dd></div><div><dt>State</dt><dd>Admitted</dd></div></dl></article><div class="limit"><small>UNKNOWN</small><p>No independent measurement source is admitted.</p></div></aside></div>
  </div>`;
  return shell('a', 'Explore', body, whyPanel('a'));
}

function onboardingA() {
  const body = `<div class="onboarding living">
    <header class="onboard-top"><div><small>SET UP WORLD INTELLIGENCE</small><h1>What should ACE understand?</h1></div><div class="chapter"><span>02 / 05</span><strong>Intent</strong></div></header>
    <div class="onboard-layout"><section class="intent"><p>Describe the changing world you need ACE to maintain. ACE will propose the model, evidence, watches, and interfaces.</p><label><span>INTELLIGENCE GOAL</span><textarea>Track how model capability and unit economics move independently, and tell me when enterprise build-versus-buy assumptions should change.</textarea></label><div class="choice-row"><button>World Intelligence <small>Release-ready</small></button><button>Daily pulse</button></div><div class="action-row"><span>Nothing is connected or activated yet.</span><button class="primary">Generate blueprint ${icons.arrow}</button></div></section>
      <aside class="blueprint"><header><div><small>PROPOSED BLUEPRINT</small><h2>ACE has drafted the intelligence system</h2></div><span class="proposal">PROPOSAL</span></header><section><small>ENTITIES</small><p>Model providers · models · evaluation suites · pricing tiers</p></section><section><small>EVENTS + SIGNALS</small><p>Release · price change · capability result · reliability result · adoption movement</p></section><section><small>QUESTIONS</small><p>Is capability-per-dollar improving? Do first-party claims hold under independent evaluation?</p></section><section><small>SOURCE PLAN</small><div class="source-plan"><span>${fixture.source}</span><b>Ready to review</b></div><div class="source-plan muted"><span>Independent measurement</span><b>Access not selected</b></div></section><footer><span>Next: source plan, predicted coverage, and explicit change review</span></footer></aside>
    </div><nav class="steps"><span>01 Choose</span><strong>02 Intent</strong><span>03 Evidence</span><span>04 Review</span><span>05 Activate</span></nav>
  </div>`;
  return shell('a', 'Build', body);
}

function overviewB() {
  const body = `<div class="overview ledger">
    <header class="folio"><div><small>WORLD INTELLIGENCE · DAILY EDITION</small><span>Fixture record · current watch window</span></div><h1>Current intelligence state</h1><p>Maintained from admitted evidence; unsupported dimensions remain explicit.</p></header>
    <div class="ledger-grid"><section class="edition"><div class="edition-no">BRIEF / 01</div><h2>${fixture.brief}</h2><p class="lede">${fixture.summary}</p><div class="annotation"><span>A</span><p><strong>Material movement.</strong> ${fixture.changed}</p><button>Why?</button></div><div class="annotation"><span>B</span><p><strong>Decision opening.</strong> ${fixture.caseBody}</p><button>Inspect</button></div><div class="annotation unknown"><span>?</span><p><strong>Evidence limit.</strong> Independent measurement is not admitted.</p><button>Source gap</button></div></section>
      <aside class="ledger-side"><section><small>DOMAIN HEALTH / 8 DIMENSIONS</small><dl class="health-ledger"><div><dt>Coverage</dt><dd>Partial</dd><span>1 admitted source role</span></div><div><dt>Freshness</dt><dd>Current</dd><span>Watch window</span></div><div><dt>Confidence</dt><dd>Not scored</dd><span>Unsupported numerically</span></div><div><dt>Conflicts</dt><dd>None admitted</dd><span>Not “none exist”</span></div><div><dt>Resolution</dt><dd>Linked</dd><span>Source → Shift → Brief</span></div><div><dt>Source health</dt><dd>Ready</dd><span>Public-web resource</span></div><div><dt>Maintenance</dt><dd>Present</dd><span>1 analyst resource</span></div><div><dt>History</dt><dd>Limited</dd><span>Current fixture window</span></div></dl></section><section class="watch"><small>WATCH / PROVIDER PRICING</small><h3>${fixture.signal}</h3><span>First-party evidence role</span></section></aside>
    </div>
  </div>`;
  return shell('b', 'Overview', body);
}

function exploreB() {
  const body = `<div class="explore ledger"><header class="ledger-query"><small>EXPLORE / QUESTION 07</small><h1>What changed in token economics?</h1><p>${fixture.changed}</p></header><div class="research-ledger"><aside class="index"><small>ANSWER INDEX</small><a class="active">01 Current answer</a><a>02 Material event</a><a>03 Provider entities</a><a>04 Evidence basis</a><a>05 Unknowns</a></aside><article class="research-answer"><small>SUPPORTED ANSWER</small><h2>${fixture.shift}</h2><p>${fixture.changed} ${fixture.matters}</p><ol class="ledger-chain"><li><span>Observation</span><p>${fixture.changed}</p></li><li><span>Event</span><p>${fixture.shift}</p></li><li><span>Signal</span><p>${fixture.signal}</p></li><li><span>Assessment</span><p>${fixture.caseBody}</p></li></ol><figure><figcaption>Focused relationship figure · depth 1</figcaption><div class="figure-graph"><b>Provider releases</b><i></i><b>Token pricing</b><i></i><b>Enterprise economics</b></div></figure></article><aside class="margin-basis"><small>BASIS NOTES</small><div><b>[1]</b><h3>${fixture.source}</h3><p>${fixture.sourceDetail}</p><span>Admitted · first-party claim</span></div><div class="note-limit"><b>[?]</b><p>Independent reliability remains untested in the fixture.</p></div></aside></div></div>`;
  return shell('b', 'Explore', body, whyPanel('b'));
}

function onboardingB() {
  const body = `<div class="onboarding ledger"><header class="dossier-head"><div><small>INTELLIGENCE DOSSIER / DRAFT 01</small><h1>World Intelligence setup</h1></div><span>02 Intent → 03 Evidence</span></header><section class="dossier"><div class="dossier-row"><span>01</span><div><small>WHAT SHOULD ACE UNDERSTAND?</small><h2>Capability and unit economics across frontier model providers</h2><p>Notify me when enterprise build-versus-buy assumptions should change.</p></div><button>Edit</button></div><div class="dossier-row"><span>02</span><div><small>GENERATED BLUEPRINT</small><div class="dossier-columns"><p><b>Entities</b>Model providers, models, pricing tiers, evaluation suites</p><p><b>Events</b>Release, price change, evaluation result, reliability result</p><p><b>Signals</b>Capability-per-dollar, claim-versus-reality</p></div></div><button>Review 8 changes</button></div><div class="dossier-row"><span>03</span><div><small>SOURCE PLAN + PREDICTED COVERAGE</small><table><tbody><tr><td>${fixture.source}</td><td>First-party claims</td><td>Proposed</td><td>Coverage estimate pending contract</td></tr><tr><td>Independent measurement</td><td>Corroboration</td><td>Access needed</td><td>Uncovered</td></tr></tbody></table></div><button>Permissions</button></div><div class="dossier-row"><span>04</span><div><small>AUTHORITY</small><p>Nothing is connected or activated. Material blueprint changes require acceptance.</p></div><button class="primary">Continue to review ${icons.arrow}</button></div></section><nav class="steps"><span>01 Choose</span><strong>02 Intent</strong><span>03 Evidence</span><span>04 Review</span><span>05 Activate</span></nav></div>`;
  return shell('b', 'Build', body);
}

function overviewC() {
  const body = `<div class="overview atlas"><header class="atlas-head"><div><small>OVERVIEW / CURRENT STATE</small><h1>${fixture.brief}</h1></div><div class="atlas-status"><span class="health-dot"></span><b>MAINTAINING</b><small>current window</small></div></header><div class="atlas-grid"><section class="atlas-main"><article class="atlas-brief"><small>ANSWER</small><p>${fixture.summary}</p><div class="atlas-actions"><button class="primary">Open Brief</button><button>Why?</button><button>Evidence</button></div></article><section class="atlas-stream"><header><small>MATERIAL MOVEMENT</small><span>RANKED / 01</span></header><div><b>01</b><article><small>SHIFT · SUPPORTED</small><h2>${fixture.shift}</h2><p>${fixture.changed}</p></article><aside><small>IMPLICATION</small><p>${fixture.matters}</p></aside></div></section><section class="atlas-bottom"><article><small>SIGNAL</small><h3>Provider pricing</h3><p>${fixture.signal}</p></article><article><small>ATTENTION</small><h3>${fixture.caseTitle}</h3><p>${fixture.caseBody}</p></article><article><small>UNKNOWN</small><h3>Independent measurement</h3><p>No source admitted.</p></article></section></section><aside class="atlas-health"><header><small>DOMAIN HEALTH</small><button>OPERATE ${icons.arrow}</button></header><dl><div><dt>Coverage</dt><dd>Partial</dd><span>1 role</span></div><div><dt>Freshness</dt><dd>Current</dd><span>watch</span></div><div><dt>Confidence</dt><dd>—</dd><span>not scored</span></div><div><dt>Conflicts</dt><dd>0</dd><span>admitted</span></div><div><dt>Resolution</dt><dd>Linked</dd><span>3 hops</span></div><div><dt>Source</dt><dd>Ready</dd><span>public web</span></div><div><dt>Maintenance</dt><dd>Present</dd><span>1 resource</span></div><div><dt>History</dt><dd>Limited</dd><span>fixture</span></div></dl></aside></div></div>`;
  return shell('c', 'Overview', body);
}

function exploreC() {
  const body = `<div class="explore atlas"><header class="atlas-query"><label>${icons.search}<input value="What changed in token economics?" aria-label="Explore query" /></label><button class="primary">Run</button><span>⌘ K</span></header><div class="atlas-explore-grid"><aside class="result-tree"><small>RESULT TREE</small><a class="active">Answer <span>1</span></a><a>Shift <span>1</span></a><a>Signal <span>1</span></a><a>Entity set <span>3</span></a><a>Evidence <span>1</span></a><a>Unknown <span>1</span></a></aside><article class="atlas-answer"><header><span>SUPPORTED ANSWER</span><small>current watch window</small></header><h1>${fixture.shift}</h1><p>${fixture.changed} ${fixture.matters}</p><button class="primary">Open Why?</button><section class="atlas-rel"><header><small>FOCUSED RELATIONSHIPS</small><select><option>Depth 1</option></select></header><div><span>Provider release</span><i></i><span>Pricing shift</span><i></i><span>Economic case</span></div><footer>Graph expansion is limited to this answer.</footer></section></article><aside class="atlas-basis"><small>BASIS / 01</small><h3>${fixture.source}</h3><p>${fixture.sourceDetail}</p><dl><div><dt>ROLE</dt><dd>First-party claim</dd></div><div><dt>STATE</dt><dd>Admitted</dd></div><div><dt>DEPTH</dt><dd>1 cited record</dd></div></dl><div class="atlas-limit"><small>LIMIT</small><p>No independent corroboration is admitted.</p></div></aside></div></div>`;
  return shell('c', 'Explore', body, whyPanel('c'));
}

function onboardingC() {
  const body = `<div class="onboarding atlas"><header class="atlas-onboard-head"><div><small>BUILD / BLUEPRINT PROPOSAL</small><h1>What should ACE understand?</h1></div><span>STEP 02 / 05 · INTENT</span></header><div class="atlas-onboard-grid"><section class="atlas-intent"><label><span>INTELLIGENCE GOAL</span><textarea>Track how model capability and unit economics move independently, and tell me when enterprise build-versus-buy assumptions should change.</textarea></label><div class="atlas-options"><button><small>DOMAIN</small><b>World Intelligence</b><span>Release-ready</span></button><button><small>CADENCE</small><b>Daily pulse</b><span>Editable</span></button></div><footer><span>No connection or authority yet.</span><button class="primary">Regenerate blueprint</button></footer></section><section class="atlas-blueprint"><header><small>GENERATED MODEL / REV 01</small><button>8 changes</button></header><div class="model-row"><span>01</span><p><b>Entities</b>Providers · models · pricing tiers · evaluation suites</p></div><div class="model-row"><span>02</span><p><b>Events</b>Release · price change · result · reliability result</p></div><div class="model-row"><span>03</span><p><b>Signals</b>Capability-per-dollar · claim-versus-reality</p></div><div class="model-row"><span>04</span><p><b>Consumers</b>Overview · cited Brief · downstream contract proposed</p></div></section><aside class="atlas-readiness"><header><small>SOURCE READINESS</small><span>0 LIVE</span></header><div><b>${fixture.source}</b><span>Proposed</span><small>Permission review next</small></div><div><b>Independent measurement</b><span>Access needed</span><small>Coverage gap</small></div><footer>Predicted coverage requires backend support.</footer></aside></div><nav class="steps"><span>01 Choose</span><strong>02 Intent</strong><span>03 Evidence</span><span>04 Review</span><span>05 Activate</span></nav></div>`;
  return shell('c', 'Build', body);
}

function narrowA() {
  return `<div class="product theme-a narrow"><header class="narrow-top"><div>${icons.mark}<strong>ACE</strong></div><button aria-label="Open menu">☰</button></header><main class="narrow-main"><button class="narrow-domain">World Intelligence ${icons.chevron}</button><nav><strong>Overview</strong><span>Explore</span><span>Build</span><span>More · 2</span></nav><section><div class="eyebrow"><span>BRIEF · CURRENT</span><span class="health-dot"></span></div><h1>${fixture.brief}</h1><p>${fixture.summary}</p><button class="primary">Read current state ${icons.arrow}</button></section><section class="narrow-health"><header><span><i class="health-dot"></i> Domain Health</span><b>Maintained with limits</b></header><div><p><small>Coverage</small>Partial · 1 role</p><p><small>Confidence</small>Not scored</p></div></section><section class="narrow-movement"><small>MATERIAL MOVEMENT · 01</small><h2>${fixture.shift}</h2><p>${fixture.changed}</p><button>Open Why? ${icons.arrow}</button></section><section class="narrow-unknown"><small>UNKNOWN</small><h3>Independent measurement</h3><p>No independent source is admitted in this fixture.</p></section></main><footer class="narrow-ask">${icons.search}<span>Ask ACE or search</span></footer><span class="direction-label">Living Brief · 390×844</span></div>`;
}

function hostFirstRunA() {
  return `<div class="first-run-product theme-a">
    <header class="first-run-brand">${icons.mark}<strong>ACE</strong><span>FIRST RUN · ONE DECISION</span></header>
    <main class="first-run-stage">
      <section class="mode-choice">
        <small>THIS COMPUTER</small>
        <h1>How should ACE run on this computer?</h1>
        <p>ACE detected the hardware and runtime. Choose the operating boundary; the model plan remains editable later.</p>
        <div class="mode-cards" role="radiogroup" aria-label="ACE operating mode">
          <button class="mode-card selected" role="radio" aria-checked="true"><span class="mode-radio"></span><div><b>Personal</b><em>RECOMMENDED</em><p>Runs on demand beside your apps and may unload the model when idle.</p></div><kbd>1</kbd></button>
          <button class="mode-card" role="radio" aria-checked="false"><span class="mode-radio"></span><div><b>Shared server</b><p>Shares resources with other workloads. Access stays local until an operator enables it.</p></div><kbd>2</kbd></button>
          <button class="mode-card" role="radio" aria-checked="false"><span class="mode-radio"></span><div><b>Dedicated appliance</b><p>This computer is exclusively ACE. Boot, recovery, and remote access are reviewed separately.</p></div><kbd>3</kbd></button>
        </div>
        <footer><span>Local only by default. No remote serving or appliance changes occur here.</span><button class="primary">Continue to Atrium ${icons.arrow}</button></footer>
      </section>
      <aside class="detected-plan">
        <header><small>DETECTED PLAN</small><span>EDIT LATER</span></header>
        <dl><div><dt>Hardware</dt><dd>Ryzen 9 7940HS · 32 GB RAM</dd></div><div><dt>Runtime</dt><dd>Linux · llama.cpp available</dd></div><div><dt>Model profile</dt><dd>Qwen3.8 27B GGUF</dd></div><div><dt>Quantization</dt><dd>Q4-class recommendation</dd></div><div><dt>Practical context</dt><dd>65,536 configured · memory-managed active window</dd></div></dl>
        <section><small>HARDWARE-SPECIFIC EXPECTATION</small><p>A comparable tested UM790 produced about 2.9 tokens/sec. This is observed deployment evidence, not a promise for this computer; ACE still runs a real generation test.</p></section>
        <footer><span class="lock-glyph">◇</span><p><b>Private starting boundary</b>Nothing is exposed beyond this computer until an operator explicitly enables it.</p></footer>
      </aside>
    </main>
    <span class="direction-label">A+C · host first run · 1440×960</span>
  </div>`;
}

function hostFirstRunNarrowA() {
  return `<div class="first-run-product first-run-narrow theme-a">
    <header class="first-run-brand">${icons.mark}<strong>ACE</strong><span>ONE DECISION</span></header>
    <main class="first-run-stage">
      <section class="mode-choice"><small>THIS COMPUTER</small><h1>How should ACE run on this computer?</h1><p>ACE detected the hardware. Choose the operating boundary.</p>
        <div class="mode-cards" role="radiogroup" aria-label="ACE operating mode"><button class="mode-card selected" role="radio" aria-checked="true"><span class="mode-radio"></span><div><b>Personal</b><em>RECOMMENDED</em><p>Runs beside your apps and may unload when idle.</p></div></button><button class="mode-card" role="radio" aria-checked="false"><span class="mode-radio"></span><div><b>Shared server</b><p>Coexists with other workloads.</p></div></button><button class="mode-card" role="radio" aria-checked="false"><span class="mode-radio"></span><div><b>Dedicated appliance</b><p>Exclusive ACE host; conversion reviewed later.</p></div></button></div>
        <details><summary>Detected plan</summary><p>32 GB RAM · llama.cpp · Qwen3.8 27B GGUF · Q4-class · 65,536 configured context</p></details>
        <footer><span>Local only by default.</span><button class="primary">Continue to Atrium</button></footer>
      </section>
    </main><span class="direction-label">A+C · 390×844</span></div>`;
}

function hostRuntimeArrivalA() {
  const body = `<div class="runtime-arrival">
    <section class="runtime-strip"><div><span class="health-dot"></span><p><small>ACE USABLE NOW</small><strong>Initial local profile passed a real generation check</strong></p></div><dl><div><dt>Recommended model</dt><dd>Downloading · 7.4 of 17.2 GB</dd></div><div><dt>Loaded</dt><dd>Not yet</dd></div><div><dt>Generation check</dt><dd>Pending for 27B profile</dd></div></dl><span class="runtime-progress"><i></i></span><b>Resumable</b></section>
    <section class="arrival-question"><small>FIRST REAL OUTCOME</small><h1>What do you need to stay ahead of?</h1><p>Start using ACE now. The recommended local model continues downloading in the background; ACE will never report it ready until a real generation succeeds.</p><label><span>INTELLIGENCE GOAL</span><textarea>Keep me ahead of material AI policy, capability, and adoption changes.</textarea></label><footer><span>Local only · mode: Personal · change later in Settings</span><button class="primary">Build this intelligence ${icons.arrow}</button></footer></section>
  </div>`;
  return shell('a', 'Overview', body);
}

const views = {
  'a-overview': overviewA,
  'a-onboarding': onboardingA,
  'a-explore': exploreA,
  'a-narrow': narrowA,
  'a-host-first-run': hostFirstRunA,
  'a-host-first-run-narrow': hostFirstRunNarrowA,
  'a-host-runtime-arrival': hostRuntimeArrivalA,
  'b-overview': overviewB,
  'b-onboarding': onboardingB,
  'b-explore': exploreB,
  'c-overview': overviewC,
  'c-onboarding': onboardingC,
  'c-explore': exploreC,
};

const requested = new URLSearchParams(location.search).get('view') || 'a-overview';
document.documentElement.dataset.view = requested;
document.querySelector('#app').innerHTML = (views[requested] || views['a-overview'])();
