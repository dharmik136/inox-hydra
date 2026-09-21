export const meta = {
  name: 'linkedin-data-layer-audit',
  description: 'Holistic audit and design of the LinkedIn capture, storage, correlation, surfacing, and modeling pipeline',
  phases: [
    { title: 'Lenses', detail: 'six independent reads of the data pipeline' },
    { title: 'Verify', detail: 'adversarially refute each lens claim against the source' },
    { title: 'Design', detail: 'ontology, dashboards, user model, roadmap' },
    { title: 'Synthesize', detail: 'single holistic picture' },
  ],
}

// Repository root. Agents run with the repo as their working directory, so a
// relative reference keeps this workflow portable across machines. Pass an
// absolute path via `args` to audit a checkout somewhere else.
const REPO = (typeof args === 'string' && args) || (args && args.repo) || '.'

const GROUND = `
You are auditing a local-first LinkedIn creator studio at: ${REPO}

ARCHITECTURE (established, do not re-derive):
- studio/extension/  Chrome MV3 extension. background.js = service worker with a
  chrome.webRequest.onCompleted listener on https://www.linkedin.com/voyager/api/*.
  content.js = DOM scraper injected on linkedin.com.
- studio/backend/    FastAPI + SQLite. app.py (2468 lines) routes; database.py (1911)
  schema; linkedin_client.py (742) ingest normalizer; crm.py (710) ICP scoring;
  intelligence_sync.py (740); scheduler.py; leads.py; repurposer.py; formatters.py.
- studio/frontend/   Vanilla JS SPA: index.html, app.js, styles.css.
- Data lands in SQLite. Tables include: analytics_daily, posts, audience_demographics,
  inspirations, queue_slots, leads, settings, lead_enrichments, media_assets,
  generation_tasks, drafts, queue_items, lead_interactions, viral_templates,
  gstack_backlog, internal_sheet_issues.

PRODUCT STANCE: the extension is meant to be a PASSIVE OBSERVER of pages the user
already loaded in their own authenticated browser. It is not meant to automate
LinkedIn actions, drive headless sessions, or fetch data the user did not themselves
request. Treat that boundary as load-bearing and real. When you propose something,
say plainly which side of it the proposal sits on.

HARD RULES:
- READ ONLY. Do not edit, write, or create any file. Do not run the app. Do not
  execute anything that opens studio/data/linkedin_studio.db for writing.
- Ground every claim in a file:line you actually read. Quote the line.
- If you believe something does NOT work, say so and cite the exact code that
  proves it. Do not soften. Do not speculate in place of reading.
- Distinguish hard ("I read the code") from inferred ("this implies").
- Never write secrets, cookies, or tokens into your output.
`

const FINDING_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['lens', 'summary', 'findings'],
  properties: {
    lens: { type: 'string' },
    summary: { type: 'string', description: '3-5 sentences: the honest state of this layer' },
    findings: {
      type: 'array',
      maxItems: 14,
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['title', 'evidence', 'why_it_matters', 'confidence', 'kind'],
        properties: {
          title: { type: 'string', description: 'one concrete claim' },
          evidence: { type: 'string', description: 'file:line plus the quoted code that proves it' },
          why_it_matters: { type: 'string', description: 'what the user loses or gains, in product terms' },
          confidence: { type: 'string', enum: ['read_the_code', 'inferred'] },
          kind: { type: 'string', enum: ['broken', 'lossy', 'missing', 'dark_data', 'opportunity', 'working_well'] },
        },
      },
    },
  },
}

const VERDICT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['refuted', 'reasoning', 'corrected_claim'],
  properties: {
    refuted: { type: 'boolean', description: 'true if the claim is wrong, overstated, or unprovable from the code' },
    reasoning: { type: 'string', description: 'cite file:line you checked' },
    corrected_claim: { type: 'string', description: 'if partly right, the precise version that survives; else empty' },
  },
}

const LENSES = [
  {
    key: 'capture',
    prompt: `LENS 1: THE CAPTURE SURFACE. Establish exactly what data physically enters this system from LinkedIn, and what does not.

Read in full: studio/extension/background.js, studio/extension/content.js,
studio/extension/manifest.json, studio/extension/sidepanel.js, studio/extension/popup.js.

Answer precisely:
1. The chrome.webRequest.onCompleted listener fires on Voyager API URLs. Examine what
   the callback actually forwards to the backend. Enumerate every field. Then answer the
   decisive question: under Manifest V3, can webRequest.onCompleted read an HTTP RESPONSE
   BODY at all? Check what "details" contains. State the consequence for this product in
   one blunt sentence.
2. content.js scrapes the creator analytics DOM. List every metric extracted and the exact
   selector. Then scrutinise the number parsing: LinkedIn renders large numbers abbreviated
   ("1.2K", "13K", "1.5M"). Trace what the parsing code does to each of those strings and
   state the numeric result.
3. content.js captures commenters and reactors. Enumerate every field captured per person
   and how each is derived. Scrutinise the company-extraction string splitting and the name
   selector fallback chain for cases that produce garbage.
4. Is any capture tied to WHICH POST the engagement happened on? Search content.js for post
   URN / post id extraction. Report what is sent as post identity and post topic.
5. The dedupe set: where does it live, and what is its lifetime across page loads and SPA
   navigations?
6. The MutationObserver: what is its scope, how often does its callback run on a live
   LinkedIn feed, and what does the debounce actually prevent versus not prevent?
7. Session cookies: trace li_at and JSESSIONID from chrome.cookies through to the backend.
   Where do they end up, and is that consistent with the passive-observer stance? Do NOT
   print any cookie value.

Be exact and quote code.`,
  },
  {
    key: 'storage',
    prompt: `LENS 2: STORAGE AND NORMALIZATION. Establish how captured data is reshaped and persisted, and what is destroyed in transit.

Read: studio/backend/linkedin_client.py (especially ingest_analytics_payload),
studio/backend/database.py (the full schema), studio/backend/migrations.py,
studio/core/telemetry_shard.py, and the /api/analytics/ingest route in app.py.

Answer precisely:
1. Walk the ingest payload through every transformation to its final rows. What is the
   grain of analytics_daily (one row per WHAT)? What time resolution is preserved, and
   what is irreversibly lost by that grain?
2. The posts table has impressions/reactions/comments/shares/clicks columns. Search the
   ENTIRE backend and extension for anything that writes those columns with real LinkedIn
   data. Report honestly whether per-post performance is ever populated from live data.
3. audience_demographics: what writes it, is anything in the live capture path capable of
   producing it, and what is its update semantics (delete-then-insert? accumulate?).
4. lead_interactions has post_id and post_urn columns. Search for every writer. Are they
   ever populated with a real value?
5. Identity and dedupe: how is a person identified across captures? Examine the linkedin_urn
   unique index and the synthetic-URN fallback the extension generates when profile_url is
   missing. What happens to identity resolution when the same person is captured twice, once
   with a profile URL and once without?
6. The telemetry shard: what does it store, what is its retention, and is anything ever read
   back OUT of it for analysis, or is it write-only?
7. Name every table or column that is written but never read, and every one read but never
   written. Grep to prove each.
8. Assess the schema as a data model: what questions can it answer today, and name the
   specific questions it structurally CANNOT answer regardless of how much data accumulates.`,
  },
  {
    key: 'correlate',
    prompt: `LENS 3: CORRELATION AND INFERENCE. Establish what the system concludes from its data, and whether those conclusions are sound.

Read: studio/backend/crm.py (the full ICPScoringEngine), studio/backend/leads.py,
studio/backend/intelligence_sync.py, studio/backend/repurposer.py,
studio/backend/formatters.py, studio/backend/agno_agent.py, and any KPI or
analytics aggregation functions in app.py and linkedin_client.py.

Answer precisely:
1. The ICP score: reproduce the full formula with every weight and keyword table. Then
   evaluate it as a model. What are its inputs, really? Is it learned or hand-tuned? Is
   there ANY feedback loop from real outcomes (did this lead convert?) back into the
   weights? Prove your answer by searching for writers of icp_score.
2. Seniority classification: list the keyword rules. Enumerate concrete real-world headlines
   that would be misclassified, including non-English, emoji-laden, and "Founder" used by
   both a solo freelancer and a Series-B CEO.
3. Every derived metric in the system (engagement_rate, velocity_score, any scores): give
   the exact formula and identify the denominator or input that can be zero, stale, missing,
   or wrong given what LENS 1 says is actually captured.
4. THE CENTRAL QUESTION: can this system answer "which of my posts produced my best leads?"
   Trace the join path from a draft/post, through lead_interactions, to a lead. State
   exactly where the chain breaks and what column would need to be populated to fix it.
5. What correlations are computable RIGHT NOW from data already on disk but are simply
   never computed? Be specific and concrete: name the tables, the join, and the insight.
6. viral_templates and intelligence_sync: where does that data come from, is it the user's
   own data or external, and what does velocity_score actually measure?`,
  },
  {
    key: 'surface',
    prompt: `LENS 4: WHAT THE USER ACTUALLY SEES. Establish the gap between what is stored and what is surfaced.

Read: studio/frontend/index.html, studio/frontend/app.js, studio/frontend/styles.css,
and the GET routes in studio/backend/app.py.

Answer precisely:
1. Enumerate every distinct view/section in the interface and the single question each one
   answers for the user. Be concrete, not decorative.
2. For every table in the SQLite schema, state whether its data reaches the screen. Name the
   DARK DATA: stored, never shown.
3. For every number displayed prominently in the UI, trace it back to its source column and
   state whether it is real captured data, a derived value, a default, or seeded demo content.
   Flag anything displayed as fact that is actually a placeholder or seed.
4. Find every place the interface makes a CLAIM to the user (safety scores, "100% safe",
   confidence percentages, tiers, "deterministic" labels, recommendations). For each, trace
   what computation backs it and judge whether the claim is warranted by that computation.
   This matters: a confident number backed by nothing is worse than no number.
5. What must the user do MANUALLY today that the stored data could do for them?
6. Where does the interface show a raw value where it should show a comparison, a trend, or a
   "so what"? Name the specific element.`,
  },
  {
    key: 'untapped',
    prompt: `LENS 5: THE UNTAPPED SURFACE. Establish what is available to a passive observer but not taken.

Read studio/extension/content.js and background.js to see what is taken today, then reason
about what a user's OWN authenticated browser session already renders and receives as they
use LinkedIn normally.

Constraint that governs this entire lens: the product stance is passive observation of pages
the user themselves loaded. Proposals that require automated navigation, background fetching,
headless sessions, bulk enumeration, or acting as the user are OUT OF BOUNDS. For every item
you propose, you must label it:
  - "passive": readable from a page the user already chose to open, at the moment they open it
  - "active": would require the software to fetch, navigate, or act on its own
Be strict and honest in that labeling. Do not launder an active technique as passive.

Answer precisely:
1. Enumerate the concrete data surfaces a creator's own browsing naturally exposes: their own
   post detail pages, their own creator analytics tabs, their own notifications, their own
   comment threads, their own profile viewers page. For each, name the specific fields visible.
2. For each surface, state what this product takes today (often nothing) and what a passive
   observer could legitimately take.
3. THE HIGHEST-VALUE MISS: identify the single most valuable field that is visible on screen
   today, requires no extra navigation, and is not being captured. Defend the choice.
4. MV3 technical reality: given webRequest cannot read response bodies, enumerate the
   legitimate mechanisms by which a passive extension can obtain STRUCTURED data (not scraped
   text) from a page the user has open. Name each mechanism, its reliability, and its failure
   modes. Be technically precise.
5. Rank every proposal by (value to the creator) / (fragility + intrusiveness). Put the
   passive, high-value, low-fragility items at the top.
6. Name the things that are genuinely NOT obtainable this way, so the roadmap does not promise
   them. Be the voice that says "no" where "no" is the truth.`,
  },
  {
    key: 'modeling',
    prompt: `LENS 6: LEARNING FROM THE DATA. Establish what could honestly be modeled, at this data scale.

Read: studio/backend/agno_agent.py, studio/backend/agno_agentos/*, repurposer.py,
formatters.py, intelligence_sync.py, crm.py, and the schema in database.py.

Critical framing: this is ONE creator's data on ONE machine. A solo creator posting daily
accumulates a few hundred posts a year and maybe a few thousand engagers. Most machine
learning proposals at this scale are fantasy. Your job is to separate what genuinely works
from what merely sounds impressive. Be the skeptic.

Answer precisely:
1. What "AI" exists in the system today? For each: is it a call to a language model, a
   hand-written heuristic, or a keyword table? Name each honestly with file:line. Flag
   anything NAMED like machine learning that is actually an if-statement.
2. Given realistic data volumes for one creator over one year, enumerate what is honestly
   learnable. For each candidate, state the minimum sample size for the result to beat a
   naive baseline, and say whether a solo creator ever reaches it. Kill the ones that do not.
3. Distinguish three classes and assign every proposal to one:
   (a) STATISTICS: computable now from tens of examples, honest, no training required
   (b) RETRIEVAL: the creator's own history as context for a language model, no training
   (c) TRAINING: genuinely requires fitting a model; state the sample size and judge feasibility
4. The single highest-value application of a language model over this creator's OWN stored
   history that is NOT currently implemented. Be concrete about the prompt inputs and the
   output, and what stored columns it needs.
5. The feedback loop problem: nothing in this system currently learns from outcomes. Design
   the minimum viable outcome-capture: what single column or table, populated how, would let
   the system start improving its own recommendations? Keep it minimal and achievable.
6. What would cause a model here to be confidently wrong, and how should the interface
   express uncertainty so the creator is not misled?`,
  },
]

phase('Lenses')
log('Reading the pipeline through six independent lenses, verifying each claim as it lands')

const lensResults = await pipeline(
  LENSES,
  (lens) => agent(`${GROUND}\n\n${lens.prompt}`, {
    label: `lens:${lens.key}`,
    phase: 'Lenses',
    schema: FINDING_SCHEMA,
    effort: 'high',
  }),
  async (result, lens) => {
    if (!result) return null
    // Verify only the load-bearing claims: things asserted broken or missing.
    const loadBearing = result.findings
      .filter((f) => ['broken', 'lossy', 'missing', 'dark_data'].includes(f.kind))
      .slice(0, 6)
    const verdicts = await parallel(
      loadBearing.map((f) => () =>
        agent(
          `${GROUND}\n\nYou are a skeptical verifier. Another agent inspected this repository and claims:\n\n` +
          `CLAIM: ${f.title}\n` +
          `THEIR EVIDENCE: ${f.evidence}\n` +
          `THEY SAY IT MATTERS BECAUSE: ${f.why_it_matters}\n\n` +
          `Open the cited files yourself and try hard to REFUTE this. Search the whole repo, ` +
          `including tests, for code that contradicts it. Common ways such a claim is wrong: ` +
          `another module writes the column they say is never written; a fallback path they ` +
          `missed handles the case; they misread which branch executes; the behaviour is ` +
          `deliberate and documented. If the claim is true but overstated, set refuted=false ` +
          `and write the precise narrower version in corrected_claim. Default to refuted=true ` +
          `if you cannot verify it from the source. Cite file:line for everything.`,
          { label: `verify:${lens.key}`, phase: 'Verify', schema: VERDICT_SCHEMA, effort: 'high' }
        ).then((v) => ({ finding: f, verdict: v }))
      )
    )
    const checked = verdicts.filter(Boolean)
    const survivors = checked.filter((c) => c.verdict && !c.verdict.refuted)
    const killed = checked.filter((c) => c.verdict && c.verdict.refuted)
    log(`${lens.key}: ${survivors.length} claims held, ${killed.length} refuted or corrected`)
    return {
      lens: lens.key,
      summary: result.summary,
      confirmed: survivors.map((c) => ({
        ...c.finding,
        refined: c.verdict.corrected_claim || null,
      })),
      refuted: killed.map((c) => ({ title: c.finding.title, why: c.verdict.reasoning })),
      // opportunities and strengths were not adversarially checked; carry them as-is
      unverified: result.findings.filter((f) => ['opportunity', 'working_well'].includes(f.kind)),
    }
  }
)

const lenses = lensResults.filter(Boolean)
const brief = JSON.stringify(lenses, null, 1)
log(`Lenses complete. Handing a verified brief of ${Math.round(brief.length / 1000)}k chars to design.`)

phase('Design')

const DESIGN_GROUND = `
You are designing the next stage of a local-first LinkedIn creator studio at ${REPO}.

Six auditors have read the codebase and their claims have been adversarially verified.
Here is the verified brief. Claims under "confirmed" survived a refutation attempt.
Claims under "refuted" did NOT survive: do not build on them.

${brief}

Design against the brief, not against a generic idea of what such a product should be.
The passive-observer boundary is real: no proposal may require the software to navigate,
fetch, or act on LinkedIn by itself. Prefer things buildable in days over things buildable
in quarters. You may read the repo to ground your design, but do NOT modify anything.
`

const designs = await parallel([
  () => agent(`${DESIGN_GROUND}

TASK: THE ONTOLOGY AND THE VOCABULARY.

This product currently uses inconsistent, partly grandiose terminology ("sovereign",
"asymmetric intelligence", "G-Stack", "anti-slop", "deterministic ICP scoring"). The user
has explicitly asked what technical vocabulary this domain needs, what we are using
correctly, and what we are missing or misusing.

Produce:
1. THE CORE ENTITY MODEL. Name the 6-9 real entities in this domain (e.g. Creator, Post,
   Impression, Engager, Interaction, Audience Segment, Outcome). For each: its identity key,
   its grain, its lifecycle, and its relationships. This is the conceptual model the schema
   should converge toward.
2. THE GRAIN TABLE. For each fact the system records, state its grain precisely
   ("one row per engager per post per interaction type"). Grain confusion is the root cause
   of several bugs in the brief: show where.
3. VOCABULARY AUDIT. A table with three columns: TERM USED TODAY | WHAT THE INDUSTRY CALLS IT
   | VERDICT. Verdict is one of: keep, rename, retire. Be direct about terms that are
   marketing language dressed as engineering. Explain what each real term means and why it
   earns its place. Cover at minimum: attribution, grain, idempotency, backfill, cohort,
   funnel, dwell time, reach vs impressions, engagement rate denominators, identity
   resolution, entity resolution, slowly changing dimension, event sourcing, lead scoring,
   propensity, survivorship bias.
4. THE MISSING VOCABULARY. Concepts this product genuinely needs a name for and does not
   have one for. Define each.
5. NAMING CONVENTIONS for future schema: how tables, event types, and metrics should be named
   so the next fifty columns do not repeat the current inconsistencies.

Be concrete and opinionated. This becomes a reference document in the repo.`,
    { label: 'design:ontology', phase: 'Design', effort: 'high' }),

  () => agent(`${DESIGN_GROUND}

TASK: THE DASHBOARDS.

Design the analytical surfaces this data can honestly support. The rule: every panel must be
backed by data the system actually has or can passively capture. If a panel needs data that
does not exist yet, say exactly what capture must land first.

Produce:
1. THE ONE-SCREEN ANSWER. If the creator opens this once a day for 30 seconds, what single
   screen earns that? Specify every element, its data source, and what decision it drives.
   Ruthlessly exclude anything that does not change a decision.
2. FIVE TO SEVEN DASHBOARDS, each specified as: the question it answers, the panels, the exact
   SQL-level data source per panel, the capture prerequisite if any, and the ACTION the creator
   takes as a result. A dashboard that produces no action is decoration: cut it.
   Consider at least: post performance and attribution, audience composition and drift,
   the engager pipeline, content pattern analysis (what actually works for THIS creator),
   timing and cadence, and a data-health panel that shows the creator what the system does
   and does not know about them.
3. THE HONESTY LAYER. The brief shows numbers displayed as fact that are seeds, defaults, or
   parse errors. Specify exactly how each surface should express provenance and confidence:
   how a seeded value looks different from a measured one, how a small sample is flagged, how
   a stale value announces its age. Design this as a reusable visual convention, not per-panel
   patches.
4. PROGRESSIVE DISCLOSURE. Day 1 the database is nearly empty; day 200 it is rich. Specify
   what each dashboard shows at n=0, n=10, n=100. An empty dashboard that says nothing is a
   product failure: design the empty state as carefully as the full one.
5. For each dashboard: the single most likely way it MISLEADS the creator, and the design
   decision that prevents it.`,
    { label: 'design:dashboards', phase: 'Design', effort: 'high' }),

  () => agent(`${DESIGN_GROUND}

TASK: THE USER AND THE ROADMAP.

The creator is a solo technical founder posting on LinkedIn to generate inbound business.
They are not a data analyst. They will not configure anything.

Produce:
1. THE JOBS. Name the 5-6 real jobs this person hires the product for, in their own words.
   For each: what they do today without the product, where it hurts, and what "done" looks like.
2. THE LOOP. Write the actual daily and weekly ritual this product should create: what happens
   at what moment, what the product does unprompted, what it asks of the creator. Be concrete
   about time of day and trigger. The product currently has capture and display but no ritual:
   design the ritual.
3. THE COMPOUNDING ASSET. Everything captured should make the NEXT post better. Trace the
   specific mechanism: engagement captured -> what is learned -> how that reaches the composer
   at the moment of writing. This closed loop is the product's actual value proposition.
   Specify it end to end.
4. FAILURE MODES OF THE USER EXPERIENCE. What makes someone abandon this in week two? Address
   each: the empty database, the browser extension that silently stops working, the numbers
   that do not match LinkedIn's own, the CRM that fills with junk names.
5. THE ROADMAP. Three horizons with explicit sequencing logic:
   - FIX (days): things currently broken or lying to the user. Order by harm.
   - FOUNDATION (weeks): the capture and schema work everything else depends on. Justify the
     order by dependency, and name what unlocks what.
   - COMPOUND (months): what becomes possible once the foundation is laid.
   For each item: the change, the files touched, the prerequisite, and how you would know it
   worked. Be specific enough that an engineer could start on Monday.
6. THE SINGLE HIGHEST-LEVERAGE CHANGE. One thing. Defend it against the other candidates.`,
    { label: 'design:user', phase: 'Design', effort: 'high' }),
])

const good = designs.filter(Boolean)
log(`Design complete: ${good.length} of 3 tracks returned. Synthesizing.`)

phase('Synthesize')

const synthesis = await agent(`You are the lead author. Produce the definitive holistic assessment of the
LinkedIn data pipeline in ${REPO}, for the product's owner: a technical solo founder who
wants the truth, not reassurance.

You have a VERIFIED AUDIT (claims that survived adversarial refutation) and THREE DESIGN
TRACKS. Your job is not to concatenate them. It is to find the through-line: the handful of
structural facts that explain most of the symptoms, and the sequence of moves that follows.

=== VERIFIED AUDIT ===
${brief}

=== DESIGN: ONTOLOGY AND VOCABULARY ===
${good[0] || '(track failed)'}

=== DESIGN: DASHBOARDS ===
${good[1] || '(track failed)'}

=== DESIGN: USER AND ROADMAP ===
${good[2] || '(track failed)'}

Write the synthesis in markdown with these sections:

1. THE THROUGH-LINE. Open with the single structural truth that explains the most symptoms.
   Name it in the first two sentences. No preamble, no throat-clearing.
2. WHAT ACTUALLY FLOWS IN. The honest data inventory: every field that genuinely enters the
   system, its source, its fidelity. Include a "believed to be captured but is not" list.
   This section must be unsparing.
3. WHERE IT BREAKS. The confirmed defects, ordered by consequence to the user, each with
   file:line. Separate "wrong" from "missing" from "never surfaced".
4. THE MODEL IT SHOULD HAVE. The entity model and the grain table, with the specific schema
   changes that move from here to there.
5. THE VOCABULARY. The audit table, kept sharp.
6. WHAT TO BUILD. The dashboards and the capture work they depend on, in dependency order.
7. WHAT TO LEARN. Statistics vs retrieval vs training, with the honest verdict on each and
   the minimum viable feedback loop.
8. THE RITUAL. How the creator actually uses this, daily and weekly.
9. THE SEQUENCE. Fix / Foundation / Compound, each item with its file, its prerequisite, and
   its test of success.
10. WHAT NOT TO BUILD. The tempting things that are fantasy at this data scale or that cross
    the passive-observer line. Say no clearly and give the reason.

Rules: cite file:line for every defect claim. Where the designs disagree, pick one and say
why in a sentence. Prefer tables over prose for anything enumerable. Do not pad. Do not
repeat a point in two sections. No em-dashes anywhere (project invariant). Write for someone
who will act on this Monday morning.`,
  { label: 'synthesis', phase: 'Synthesize', effort: 'high' })

return { synthesis, lenses, designs: good }
