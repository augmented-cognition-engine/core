// core/ui/canvas/src/app/fixtures/multiplayer.tsx
//
// Mock state that mirrors what multiplayer.html shows when the demo
// runs through to mid-deliberation. First render uses this so the
// canvas opens populated — per partner-never-asks, the partner is
// already warm, already mid-thought, already has prior context.
//
// When the live WebSocket subscription lands, useAceCoreState swaps
// to that and this fixture only lives behind a `?fixture=` debug flag.
import type { AceCoreState } from '../state'

export const multiplayerFixture: AceCoreState = {
  topbar: {
    title: 'ACE',
    subtitle: 'reasoning OS',
    warmthLabel: 'Warm',
    cost: {
      tokensUsed: 142_300,
      costUsd: 0.024,
      scope: 'this turn',
    },
    phases: [
      { id: 'frame', label: 'Frame', status: 'done' },
      { id: 'prioritize', label: 'Prioritize', status: 'done' },
      { id: 'diverge', label: 'Diverge', status: 'done' },
      { id: 'converge', label: 'Converge', status: 'done' },
      { id: 'synthesize', label: 'Synthesize', status: 'done' },
    ],
    recipe: {
      name: 'deep_committee',
      modelHint: 'Opus',
    },
    sentinel: {
      findingCount: 4,
      engineCount: 35,
      lastSweep: '38s ago',
      topSeverity: 'high',
      findings: [
        {
          id: 'f1',
          category: 'Gap analyzer',
          severity: 'high',
          headline: (
            <>
              <b>Accessibility floor is 0.30</b> — gap of 0.30 below the 0.60
              target. 55 active gaps in error handling, semantic markup, and
              focus management blocking 15 demo patterns.
            </>
          ),
          okr: 'blocks OKR · Accessibility ≥ 0.6',
        },
        {
          id: 'f2',
          category: 'Gap analyzer',
          severity: 'medium',
          headline: (
            <>
              <b>Observability avg 0.28 with 248 gaps.</b> No structured
              logging on 18 of 35 critical paths. Telemetry score declining
              (−0.07 this week).
            </>
          ),
          okr: 'no OKR link · candidate for Q3',
        },
        {
          id: 'f3',
          category: 'Gap analyzer',
          severity: 'low',
          headline: (
            <>
              <b>Documentation avg 0.24.</b> 132 gaps across reference +
              onboarding. Not load-bearing but compounds when onboarding
              pipeline activates.
            </>
          ),
        },
        {
          id: 'f4',
          category: 'Briefing',
          severity: 'low',
          headline: (
            <>
              <b>Weekly briefing ready · 2026-05-14 23:31.</b> 83 engines
              collapsed into a single narrative; 20 insights verified, 0
              corrections, 0 contradictions surfaced.
            </>
          ),
        },
      ],
    },
    memory: {
      patternCount: 7,
    },
    roster: [
      { lens: 'architecture' },
      { lens: 'security' },
      { lens: 'data' },
      { lens: 'ux' },
      { lens: 'product_strategy' },
    ],
  },
  vision: {
    goal: 'Ship the open-source reasoning OS that democratizes high-quality LLM usage.',
    okrs: [
      {
        id: 'okr-launch',
        label: 'OSS launch · Q3',
        progress: 0.62,
        status: 'advancing',
        detail:
          'Ship ACE core (Apache) by end of Q3 with reference UI, engine, MCP server, and at least one published extension as worked example.',
        recentCommits: [
          { id: 'c1', date: 'May 26', what: 'Structural reorg + Phase B canvas rebuild' },
          { id: 'c2', date: 'May 25', what: 'Design system stable: 184 tokens, 21 primitives' },
          { id: 'c3', date: 'May 24', what: 'Open-core strategy locked' },
        ],
      },
      {
        id: 'okr-design-partners',
        label: '3 design partners',
        progress: 0.33,
        status: 'advancing',
        detail:
          'Recruit three design partners actively using ACE to build extensions and feeding back on the partnership thesis. The flagship extension team is partner 1.',
        recentCommits: [
          { id: 'c1', date: 'May 20', what: 'First design-partner engagement formalized' },
          { id: 'c2', date: 'May 18', what: 'Consulting-led GTM posture confirmed' },
        ],
      },
      {
        id: 'okr-calibration',
        label: 'Calibration ≥ 0.80',
        progress: 0.84,
        status: 'advancing',
        detail:
          'L9 calibration layer targets ≥ 0.80 mean accuracy across a rolling 12-prediction window. Currently 0.78 mean as resolved forecasts build a product-specific evidence record.',
        recentCommits: [
          { id: 'c1', date: 'May 22', what: 'Calibration history surface lands' },
          { id: 'c2', date: 'May 14', what: 'Reconciliation loop ships' },
        ],
      },
    ],
  },
  briefMeBack: {
    lede: 'Since you were last here, the sentinel flagged a contradiction between the cache-layer decision and the latency-floor prediction. The committee is convening on whether to revisit.',
    bullets: [
      {
        id: 'b1',
        text: 'Architecture noticed the cache-layer assumption may not hold at 50 RPS — wants to reopen.',
      },
      {
        id: 'b2',
        text: 'Data lens flagged a Y-shape break in the calibration curve from last Tuesday — could be measurement, could be real.',
      },
      {
        id: 'b3',
        text: '2 prior decisions closed on the +30d horizon — both within calibration tolerance.',
      },
    ],
  },
  canvas: {
    inFlight: true,
    banner: {
      active: true,
      horizonLabel: '+30d',
      decisionTitle: (
        <>
          Your call to <b>defer the cache layer</b> reconciles in 4 days —
          observed p95 within tolerance so far.
        </>
      ),
      outcomeHint: 'on track · 92% likely calibrated',
    },
    sections: [],
    presence: {
      partnerStatus: 'thinking',
      partnerActivity: 'Holding for your call',
      participants: [
        {
          id: 'user',
          name: 'You',
          initial: 'E',
          accent: 'var(--ace-ink)',
          status: 'listening',
          isUser: true,
        },
        {
          id: 'partner',
          name: 'Partner',
          initial: '◇',
          accent: 'var(--ace-accent)',
          status: 'active',
          activity: 'Asked you about the UX seam',
          isPartner: true,
        },
        {
          id: 'architecture',
          name: 'Architecture',
          initial: '◌',
          accent: '#5B7A99',
          status: 'just-spoke',
          lastAt: '12 min ago',
        },
        {
          id: 'security',
          name: 'Security',
          initial: '◈',
          accent: '#8C3A3A',
          status: 'just-spoke',
          lastAt: '9 min ago',
        },
        {
          id: 'data',
          name: 'Data',
          initial: '≈',
          accent: '#5F7A4F',
          status: 'just-spoke',
          lastAt: '6 min ago',
        },
        {
          id: 'ux',
          name: 'UX',
          initial: '◐',
          accent: '#C26648',
          status: 'active',
          activity: 'Examining asymmetric landing',
        },
        {
          id: 'product_strategy',
          name: 'Product Strategy',
          initial: '◆',
          accent: '#C49348',
          status: 'idle',
          lastAt: 'not yet',
        },
      ],
    },
    readoutHeader: 'The team is mid-deliberation · 12 min in',
    contributions: [
      {
        id: 'architecture',
        lens: 'architecture',
        speaker: 'Architecture',
        accent: '#5B7A99',
        framing:
          'The cache-layer assumption is shaky at 50 RPS. The y-axis is fixed at memory pressure, but the real constraint is the eviction tail-latency — and that doesn’t hold linearly past the threshold.',
        confidence: 0.82,
        landedAt: '12 min ago',
      },
      {
        id: 'security',
        lens: 'security',
        speaker: 'Security',
        accent: '#8C3A3A',
        framing:
          'If we defer the cache, the auth-token revalidation window grows. It’s not a breach risk — it’s a measurable degradation in the trust window. Worth flagging, not worth blocking.',
        confidence: 0.78,
        landedAt: '9 min ago',
      },
      {
        id: 'data',
        lens: 'data',
        speaker: 'Data',
        accent: '#5F7A4F',
        framing:
          'The Y-shape break in the calibration curve is a real regime shift, not instrumentation noise. Traffic distribution moved from long-tail to bimodal over the last nine days.',
        confidence: 0.84,
        landedAt: '6 min ago',
      },
      {
        id: 'ux',
        lens: 'ux',
        speaker: 'UX',
        accent: '#C26648',
        framing:
          'Given the bimodal traffic, the cache-layer change lands asymmetrically. Power users see the wins; casual users see only the latency-floor drop. We’d be optimizing for one tail of the distribution — and the casual tail is where the trust',
        confidence: 0.62,
        inFlight: true,
        thinkingAbout: 'whether casual-user latency-floor drop is worse than the asymmetric win',
      },
    ],
    attention: [
      {
        id: 'partner-ux-seam',
        speaker: 'Partner',
        accent: 'var(--ace-accent)',
        initial: '◇',
        question: (
          <>
            Heads up — UX is wavering on the asymmetric landing, and{' '}
            <b>I think this is the load-bearing call</b>. You’ve weighted
            compliance and the casual-user tail heavily in past decisions.
            Want to put your thumb on the scale before we commit, or trust
            the team to land it?
          </>
        ),
        triggeredBy:
          'Confidence on the UX read sitting at 0.62 — below the 0.70 threshold I usually let through',
        askedAt: 'just now',
        onReply: (text) => {
          // eslint-disable-next-line no-console
          console.log('[attention-reply]', text)
        },
        quickActions: [
          { id: 'push-back', label: 'push back', onClick: () => {} },
          { id: 'trust-team', label: 'trust the team', onClick: () => {} },
        ],
      },
    ],
    proactive: {
      sentinel: {
        headline: (
          <>
            <b>Accessibility floor at 0.30</b> — 55 active gaps across
            error_handling, semantic markup, focus management. Not blocking
            this deliberation, but compounds when onboarding ships.
          </>
        ),
        severity: 'high',
        noticedAt: '38s ago',
      },
      newMemory: {
        pattern: (
          <>
            <b>Bimodal traffic shape changes trade-off calculus.</b> Captured
            from this turn — power-user concentration shifts the where-do-
            wins-land question.
          </>
        ),
        provenance: 'pattern · seen in 3 prior decisions · last 2026-04-22',
      },
      patternEmerge: {
        observation: (
          <>
            You weight <em>compliance heavily</em> — accept higher friction
            for audit-readiness. Seen across 4 decisions over the last 90
            days; drove the Q1 + Q2 cache decisions too.
          </>
        ),
        provenance: 'preference · 4× confirmations · drove 2026-01 + 2026-03',
      },
      calibration: {
        values: [0.62, 0.71, 0.68, 0.78, 0.74, 0.82, 0.86, 0.8, 0.85, 0.83, 0.88, 0.84],
        average: 0.78,
        note:
          'Last 12 predictions, reconciled at horizon. Calibration reflects the product-specific record of forecast versus observed outcome.',
      },
    },
    // No convergence block — the deliberation hasn't landed yet.
    // ConvergenceBeat renders nothing when state.convergence is undefined.
  },
  workingPanel: {
    agentsInFlight: [],
    capturedThisTurn: {
      decisions: 1,
      perspectives: 5,
      contributions: 11,
    },
  },
  footer: {
    placeholder: 'redirect, push back, or ask a follow-up…',
    onAsk: (text) => {
      // eslint-disable-next-line no-console
      console.log('[ask-the-team]', text)
    },
  },
  // Sample orchestra — what's weighing in on the deliberation in the fixture.
  // Will be replaced by useLiveComposition's WebSocket payload once a session
  // is connected; this seeds the surface so the CompositionLens has content
  // out of the box.
  composition: {
    meta_skills: [
      'strategic_intelligence',
      'risk_intelligence',
      'planning_intelligence',
      'communication_intelligence',
      'domain_specific_intelligence',
    ],
    depth: 3,
    fusion_mode: false,
    classification: {
      task_type: 'plan',
      discipline: 'product_strategy',
      mode: 'deliberative',
      archetype: 'advisor',
      complexity: 'complex',
    },
  },
  // The Deliberation Journey — the substrate made visible. Renders L1→L9
  // end-to-end on a real-shaped task: a strategic decision about pivoting
  // the homepage hero from price-first to outcomes-first for Q3.
  // Tracks correspond to active meta-intelligences (L4 deep committee
  // parallel lenses). Synthesis line at the bottom of each stage is L6's
  // cross-discipline implication chain. Convergence stages carry L7
  // decisions and L9 predictions. Ambient sentinel marks (L8) live in the
  // pinned-notes rail.
  journey: {
    topic:
      'Should we pivot the homepage hero from price-first to outcomes-first for the Q3 launch?',
    classification: {
      discipline: 'product_strategy',
      taskType: 'plan',
      mode: 'deliberative',
      archetype: 'advisor',
      complexity: 'complex',
      confidence: 0.86,
      depth: 3,
      fusionMode: false,
      metaSkills: [
        'strategic_intelligence',
        'risk_intelligence',
        'planning_intelligence',
        'communication_intelligence',
        'domain_specific_intelligence',
      ],
      tools: [
        // ACE substrate
        { slug: 'ace_search', label: 'ace_search', category: 'ace', description: 'search the decision graph + intelligence layer', active: true },
        { slug: 'ace_load', label: 'ace_load', category: 'ace', description: 'load prior context for a topic / domain', active: true },
        { slug: 'ace_capture_decision', label: 'ace_capture_decision', category: 'ace', description: 'record a decision with rationale + alternatives' },
        { slug: 'ace_blast_radius', label: 'ace_blast_radius', category: 'ace', description: 'trace what a change touches via the capability graph' },
        { slug: 'ace_active_composition', label: 'ace_active_composition', category: 'ace', description: 'introspect the current orchestra of meta-skills' },
        // Codebase
        { slug: 'grep_repo', label: 'grep_repo', category: 'code', description: 'search source files for a pattern or symbol' },
        { slug: 'read_file', label: 'read_file', category: 'code', description: 'open a file at a path' },
        { slug: 'ace_code_context', label: 'ace_code_context', category: 'code', description: 'LSP-grounded code symbols + calls + references' },
        // Web
        { slug: 'web_search', label: 'web_search', category: 'web', description: 'lookup external sources and current information', active: true },
        { slug: 'ace_research', label: 'ace_research', category: 'web', description: 'multi-mode research pipeline with confidence scoring' },
        // Data
        { slug: 'ace_findings', label: 'ace_findings', category: 'data', description: 'sentinel findings + recent observations' },
        { slug: 'ace_calibration', label: 'ace_calibration', category: 'data', description: 'archetype calibration scores from L9 reconciliation' },
        // External
        { slug: 'ext_brief_composer', label: 'ext · brief_composer', category: 'external', description: 'compose a B2B audit brief in the extension surface' },
        { slug: 'ext_sentinel', label: 'ext · sentinel', category: 'external', description: 'continuous monitoring across the marketing surface' },
      ],
    },
    stages: [
      {
        id: 'prep',
        phase: 'prep',
        glyph: '⌖',
        title: 'Prep · classify the ask',
        subtitle: 'intake & route',
        status: 'past',
        tracks: [
          {
            metaSkill: 'classifier',
            label: 'L2 classifier',
            contribution:
              'product_strategy · deliberative · depth 3 · advisor. Confidence 0.86. Routed to strategic + risk + planning + communication.',
            instrument: 'multi-dimension-classifier',
          },
        ],
        synthesis: {
          implication:
            'A live positioning question, not a tactical hero swap. Routed deep so the committee can weigh consumption-narrative vs AI-buyer-language tensions explicitly.',
        },
      },
      {
        id: 'frame',
        phase: 'frame',
        glyph: '◯',
        title: 'Frame · capability map',
        subtitle: 'what is in scope',
        status: 'past',
        capabilityGraph: {
          nodes: [
            { id: 'brand', label: 'brand voice', state: 'load-bearing' },
            { id: 'sales', label: 'sales contract', state: 'load-bearing' },
            { id: 'narrative', label: 'narrative', state: 'load-bearing' },
            { id: 'pricing', label: 'pricing', state: 'out-of-scope' },
            { id: 'delivery', label: 'delivery infra', state: 'out-of-scope' },
          ],
          edges: [
            { from: 'brand', to: 'narrative' },
            { from: 'sales', to: 'narrative' },
            { from: 'brand', to: 'sales', dashed: true },
            { from: 'pricing', to: 'delivery' },
          ],
        },
        tracks: [
          {
            metaSkill: 'strategic_intelligence',
            label: 'strategic',
            accent: 'var(--ace-accent-advisor, #5a7)',
            contribution:
              'Three framings: pure positioning · investment-allocation claim · audience narrative. Positioning is the live one because consumption is the 18-month investment story we already told sales.',
            instrument: 'problem-space-modeling',
            confidence: 0.82,
          },
          {
            metaSkill: 'communication_intelligence',
            label: 'communication',
            accent: 'var(--ace-accent-creator, #58c)',
            contribution:
              'Audience: enterprise AI buyers in Q3 demos. Their language is AI-first. Brand voice already shifted past the consumption claim in three out of the last five posts.',
            instrument: 'audience-modeling',
            confidence: 0.75,
          },
        ],
        synthesis: {
          implication:
            'Load-bearing constraints: sales contract on consumption-first language, brand voice already drifting AI-first, Q3 buyers expect AI-first hero copy. Pricing + delivery infrastructure are out of scope.',
          tension:
            "Sales contract is the strongest signal AGAINST a clean pivot — narrative is the strongest signal FOR. They're both load-bearing.",
        },
      },
      {
        id: 'choose',
        phase: 'choose',
        glyph: '◇',
        title: 'Choose · four positions',
        subtitle: 'diverge across lenses',
        status: 'current',
        matchedSignalsByMetaSkill: {
          strategic_intelligence: [
            'pivot',
            'positioning',
            'tradeoff',
            'should we',
            'market',
          ],
          risk_intelligence: ['pivot', 'risk', 'cost', 'failure', 'comp'],
          planning_intelligence: ['Q3', 'sequence', 'roadmap', 'phase'],
          communication_intelligence: [
            'hero',
            'message',
            'voice',
            'audience',
            'positioning',
          ],
          domain_specific_intelligence: ['enterprise', 'buyer', 'Q3', 'AI'],
        },
        workingSignals: [
          { metaSkill: 'strategic_intelligence', label: 'strategic', state: 'just-spoke', whenLabel: '8s ago' },
          { metaSkill: 'risk_intelligence', label: 'risk', state: 'just-spoke', whenLabel: '5s ago' },
          { metaSkill: 'planning_intelligence', label: 'planning', state: 'just-spoke', whenLabel: '3s ago' },
          { metaSkill: 'communication_intelligence', label: 'communication', state: 'typing' },
        ],
        tracks: [
          {
            metaSkill: 'strategic_intelligence',
            label: 'strategic',
            accent: 'var(--ace-accent-advisor, #5a7)',
            contribution:
              'Pivot fully. Q3 enterprise AI buyers are the biggest revenue pool open right now and our positioning has to meet them in their language.',
            instrument: 'strategy-pairwise',
            confidence: 0.88,
          },
          {
            metaSkill: 'risk_intelligence',
            label: 'risk',
            accent: 'var(--ace-accent-sentinel, #c44)',
            contribution:
              "Don't pivot in Q3. Sales contract treats consumption-first as the 18-month claim; pivoting now triggers comp renegotiation. Cost ~$1.2M and 3 quarters of friction.",
            instrument: 'fmea',
            confidence: 0.81,
          },
          {
            metaSkill: 'planning_intelligence',
            label: 'planning',
            accent: 'var(--ace-accent-executor, #58c)',
            contribution:
              'Hybrid sequence: AI-first hero copy at Q3 launch, consumption-first remains the sales motion. Re-evaluate at Q1 with three quarters of buyer-signal data.',
            instrument: 'risk-first-ordering',
            confidence: 0.79,
          },
          {
            metaSkill: 'communication_intelligence',
            label: 'communication',
            accent: 'var(--ace-accent-creator, #58c)',
            contribution:
              "Brand voice is already mostly there. Pivot the hero card and lead-magnet copy; let the deeper sales decks carry consumption framing until comp catches up.",
            instrument: 'framing-selection',
            confidence: 0.77,
            inFlight: true,
          },
        ],
        synthesis: {
          implication:
            'Strategic, planning, and communication converge on a partial pivot: AI-first on the public surfaces, consumption-first held in the sales motion until Q1 calibration arrives.',
          tension:
            'Risk dissents — the partial pivot still leaks into the sales contract through prospect references. Either accept the risk explicitly or wait one more quarter.',
          leveragePoint:
            'The hero card and lead-magnet copy. Largest narrative shift with smallest sales-contract exposure.',
        },
        forkTrace: {
          runId: 'reasoning_run:demo-choose',
          checkpointSeq: 2,
          recommendation: 'fork',
          original: {
            label: 'original',
            lens: 'choose',
            score: 0.61,
            conclusion:
              'Partial pivot: AI-first on the public surfaces, consumption-first held in the sales motion until Q1 calibration.',
          },
          best: {
            label: 'adversarial',
            lens: 'adversarial',
            score: 0.79,
            conclusion:
              'Reframe so there is no pivot to leak: lead with consumption PROOF and cast AI as what makes the proof move. One narrative across public + sales — Risk’s dissent disappears.',
          },
          forks: [
            {
              label: 'adversarial',
              lens: 'adversarial',
              score: 0.79,
              conclusion:
                'Reframe so there is no pivot to leak: lead with consumption PROOF and cast AI as what makes the proof move. One narrative across public + sales — Risk’s dissent disappears.',
            },
            {
              label: 'systems',
              lens: 'systems',
              score: 0.52,
              conclusion:
                'Treat positioning as a feedback loop: ship AI-first publicly, but wire the Q1 calibration signal back into the sales script so the two surfaces converge instead of diverging.',
              capabilityDeltaScore: 0.68,
            },
          ],
        },
      },
      {
        id: 'validate',
        phase: 'validate',
        glyph: '◇',
        title: 'Validate · stress the choice',
        subtitle: '1× / 10× / 100× failure',
        status: 'future',
        tracks: [
          {
            metaSkill: 'risk_intelligence',
            label: 'CFO Mode',
            accent: 'var(--ace-accent-sentinel, #c44)',
            contribution:
              'Stress test: three brand-positioning shifts in 2025 each caused short-term ICP drift — all recovered only when a proof bar kept the prior message alive on-page. CIO-segment perception drift is ~2× the upside if the proof bar sits below the fold.',
            instrument: 'fmea',
            confidence: 0.9,
          },
          {
            metaSkill: 'planning_intelligence',
            label: 'planning',
            accent: 'var(--ace-accent-executor, #58c)',
            contribution:
              '1× — hero copy ships, minor sales friction. 10× — CIO renewals cite "direction change" in QBRs. 100× — comp renegotiation reopens mid-year. A consumption proof-bar above the fold collapses the 10× and 100× modes back toward 1×.',
            instrument: 'risk-first-ordering',
            confidence: 0.8,
          },
        ],
        sentinel: [
          {
            severity: 'high',
            source: 'sentinel',
            headline:
              'Contradiction: the AI-first proposal reverses the 2025-11 "consumption-first" positioning decision. Surfaced for an explicit override, not a silent reversal.',
          },
        ],
        synthesis: {
          implication:
            'The choice survives validation IF a consumption proof-bar sits above the fold — that single mitigation neutralizes the CIO-drift failure mode at every scale.',
          tension:
            'Sentinel holds an open contradiction against the 2025-11 decision; shipping requires an explicit supersession.',
        },
      },
      {
        id: 'critique',
        phase: 'critique',
        glyph: '◆',
        title: 'Critique · decide + commit',
        subtitle: 'capture decision + prediction',
        status: 'future',
        tracks: [
          {
            metaSkill: 'strategic_intelligence',
            label: 'strategic',
            accent: 'var(--ace-accent-advisor, #5a7)',
            contribution:
              'Commit to the hybrid: AI-first hero on the public surfaces with a consumption proof-bar above the fold; consumption-first stays the sales motion until Q1 calibration. Supersede the 2025-11 decision explicitly.',
            instrument: 'synthesis',
            confidence: 0.86,
          },
        ],
        decisions: [
          {
            id: 'dec:outcomes-first-hero',
            title: 'Ship outcomes-first homepage hero with a pricing proof-bar above the fold',
            rationale:
              'AI-buyer segment grew 47% YoY vs 3% for CIO; AWS/Azure/Dell all led AI-first in Q1–Q2. The proof bar neutralizes the 2× CIO-drift risk the CFO and Sentinel flagged. Consumption stays the sales motion until Q1 data lands.',
            confidence: 0.84,
            cited: ['strategic', 'communication', 'CFO Mode', 'sentinel'],
          },
        ],
        prediction: {
          horizonDays: 90,
          forecast:
            'Outcome-buyer engagement on the homepage hero rises ≥25% by Q1 with no net CIO-segment renewal drop.',
          falsifyIf:
            'CIO-segment renewals decline >2 points, OR AI-buyer engagement is flat at the 90-day mark.',
        },
        synthesis: {
          implication:
            'Decision captured and a falsifiable 90-day prediction attached — the committee converged on the hybrid, with the proof-bar mitigation as the load-bearing condition.',
        },
      },
    ],
    priorDecisions: [
      {
        id: 'd:homepage-positioning-2025',
        title: 'Homepage positioning leads with price (Q3 2025)',
        cited: ['strategic', 'brand'],
      },
      {
        id: 'd:enterprise-ai-buyer-language',
        title: 'Adopt AI-first language for enterprise-AI buyer segments',
        cited: ['communication', 'researcher'],
      },
      {
        id: 'd:sales-comp-contract-2026',
        title: 'Sales comp tied to consumption-volume targets through FY26',
        cited: ['risk', 'planning'],
      },
    ],
    ambientSentinel: [
      {
        severity: 'medium',
        source: 'perspective_gaps',
        headline:
          'Brand voice has shifted AI-first in 3 of last 5 posts; consumption framing weakening.',
      },
      {
        severity: 'low',
        source: 'competitive_observer',
        headline:
          'Snowflake and Databricks both led their Q2 narratives with AI-first hero cards.',
      },
    ],
  },
}
