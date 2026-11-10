# AI-Powered Ad Campaign Manager — Product Requirements Document

> Document 4 · Status: DRAFT (requirements only) · Last updated: 6 Oct 2026
> Related: Platform Selection (Doc 1), High-Level Design (Doc 2), LLM Selection (Doc 3), Tech Stack, LLD, Implementation Roadmap (`.claude/plans/`)

## Problem

Small teams that want to advertise on Instagram must learn Meta Ads Manager's campaign structure, targeting options, copy rules and reporting before they can run even one campaign. Most of them either don't advertise, or launch poorly targeted ads and can't tell from raw numbers whether the ads work or what to change. The cost is wasted ad spend, or no advertising at all.

## Evidence

- The internship brief defines this problem and the required capabilities. It is the source of every requirement below.
- Assumption — needs validation via **user interviews with 3–5 small-business owners or marketers**: that a guided conversation is faster and less error-prone for them than Ads Manager.
- Assumption — needs validation via **usability testing of the prototype**: that users trust an AI-proposed campaign enough to approve it after review.

## Users

- **Primary:** a founder, solo marketer or small-business owner with a product to promote, a budget, and little Meta Ads experience. The need is triggered by a launch or a promotion they want to run now.
- **Secondary:** the internship evaluator, who must be able to run the whole flow from the documentation and inspect its decisions.
- **Not for:** agencies managing many client accounts, performance marketers who need full Ads Manager control, and advertisers in Meta's special ad categories (housing, employment, credit, politics).

## Hypothesis

We believe **a conversational agent that turns a plain-language brief into a reviewed Instagram ad campaign (run through Meta's ads platform), publishes it only after explicit approval, and explains its performance in plain language** will **let non-experts launch and improve ad campaigns safely** for **small-business owners and solo marketers**.

We'll know we're right when **a first-time user goes from brief to an approved, published (paused) campaign in under 15 minutes without opening Ads Manager, and zero campaigns are ever published or changed without a matching recorded approval.**

## Success Metrics

| # | Metric | Target | How measured |
|---|---|---|---|
| M1 | Time from first message to approved campaign (complete brief) | ≤ 15 min median | Timestamps in the audit log, usability sessions |
| M2 | Clarifying questions for a complete brief | ≤ 2 rounds | Evaluation briefs |
| M3 | Unapproved external actions (publish, activate, live change) | **0** (hard requirement) | Audit log check + approval-gate tests |
| M4 | Requirement extraction accuracy | ≥ 90% of fields correct | Evaluation set of 10 golden briefs |
| M5 | Generated ads breaking copy rules that reach the user | 0 | Validation logs |
| M6 | Publish success on first attempt (sandbox) | ≥ 95% | Publish run records |
| M7 | Report statements whose numbers match the stored data | 100% | Grounding check results |
| M8 | Recovery after an injected publish failure | 100% complete, 0 duplicate Meta objects | Failure-injection test |
| M9 | User-rated clarity of performance explanations | TBD — needs validation via usability testing (5-point scale) | Post-session survey |

## Scope

**MVP** — ads run on **Instagram only** (feed and Explore). One user connects their Meta ad account, Facebook Page and linked Instagram professional account. Through chat they describe a campaign, answer the questions about what's missing, and review a proposed campaign with 2–3 ad variants. They revise it until they're happy, approve it, publish it (created paused), and activate it with a second confirmation. They then see collected metrics, a plain-language performance report, and improvement proposals they can approve or reject.

**Out of scope**

- Platforms other than Meta, and Facebook placements — the batch is locked to Meta; we place ads on Instagram only.
- Instagram Stories and Reels placements — they need 9:16 creative; v1 uses feed-shaped images.
- Lead-form and sales/conversion objectives — they need lead forms or a tracking pixel. v1 covers website-traffic campaigns (awareness optional).
- AI-generated images and video — v1 generates image *concepts*; the user uploads the image.
- Changes to live campaigns without approval — excluded by design, even if users ask for "autopilot".
- Teams, roles and multi-user approval — one owner per campaign in v1.
- Billing, invoicing, mobile apps.

## Functional Requirements

Each requirement maps to a capability in the brief (B1–B10).

| ID | Requirement | Acceptance criteria | Brief |
|---|---|---|---|
| FR-1 | The user can describe a campaign in plain language | Product, objective, audience, geography, budget, duration and landing page are captured when stated | B1 |
| FR-2 | The system asks only for what is missing or invalid | A brief missing the budget and URL gets one targeted question covering both; nothing invented is treated as confirmed | B1 |
| FR-3 | Values the system inferred are shown for confirmation | Inferred values are marked "proposed" until the user confirms them | B1 |
| FR-4 | The system proposes a campaign plan | The plan shows objective, audience (with an estimated size), budget split and schedule, and only uses targeting options that exist on Meta | B2 |
| FR-5 | The system generates 2–3 ad variants | Each has a headline, main text, description, call to action and image concept, within the display limits | B3 |
| FR-6 | Invalid or unsafe generated content never reaches review silently | Over-length or policy-breaking text is fixed automatically or shown to the user as an error | B3 |
| FR-7 | The user can request changes in plain language | "Change headline 1 to …" produces a new version with only that change, and the changes are shown side by side | B4, B5 |
| FR-8 | Every version is kept | The user can view any earlier version and its differences | B5 |
| FR-9 | Nothing is published without explicit approval of the exact version on screen | Chat messages never count as approval; editing after approval cancels it | B4, B6 |
| FR-10 | Approved campaigns are created on Meta, paused | The campaign, ad set and ads appear in the user's ad account as paused | B6 |
| FR-11 | Activation needs a second confirmation | Ads start delivering only after the user confirms Activate | B6 |
| FR-12 | Publishing failures are visible and recoverable | The user sees the platform's error and can resume without creating duplicates, or discard | B6 |
| FR-13 | Metrics are collected automatically and kept over time | Impressions, reach, clicks, CTR, spend, CPC, CPM and frequency per ad per day, refreshed several times a day | B7 |
| FR-14 | Simulated data is always labelled | When test accounts can't deliver ads, any simulated metrics are clearly marked | B7 |
| FR-15 | Performance is explained, not just shown | The report separates facts, calculations, assumptions and recommendations, and states the date range and data limitations | B8, B9 |
| FR-16 | Improvements are proposed with reasons | Proposals (pause an ad, adjust budget, new creative, targeting suggestion) cite the data behind them | B9, B10 |
| FR-17 | Improvements are applied only after approval and within limits | Budget changes are capped per change and never exceed the approved total | B10 |
| FR-18 | Every decision and external action is traceable | The user can view a time-ordered audit trail for each campaign | All |
| FR-19 | Ad review problems are surfaced | If Meta disapproves an ad, the user sees the reason and a suggested fix | B9 |
| FR-20 | Ads run on Instagram with the user's own Instagram identity | Ads appear only in Instagram feed/Explore under the linked Instagram account; images Instagram can't use are rejected at upload with a clear reason | B6 |

## Non-Functional Requirements

| ID | Area | Requirement |
|---|---|---|
| NFR-1 | Security | No social-media passwords are ever requested or stored; platform access uses the platform's OAuth; tokens are encrypted at rest |
| NFR-2 | Security | Users can never see or act on another user's campaigns or connections |
| NFR-3 | Safety | Text from users, web pages or the platform can never cause publishing, activation or spending |
| NFR-4 | Reliability | No duplicate campaigns or ads from retries, double clicks or restarts |
| NFR-5 | Reliability | Failures leave the campaign in a known state with a clear next action |
| NFR-6 | Observability | Every model call, tool call, approval and platform call is logged with a shared request ID |
| NFR-7 | Performance | A chat reply arrives within 10 s at the median (TBD — confirm after the model evaluation) |
| NFR-8 | Operability | Another developer can run the system locally from the README in under 30 minutes |
| NFR-9 | Maintainability | Platform API version and model names are configuration, not code |
| NFR-10 | Accessibility | Core flows are keyboard-usable, with visible focus and text labels for status colours |

## Constraints

- Platform fixed for the batch: Meta's official Marketing API; placement: Instagram (feed + Explore) in v1.
- The user needs a Facebook Page with a linked Instagram professional account.
- Agent framework: Google ADK (chosen so more agents can be added later).
- Test ad accounts never deliver ads; real metrics require a real account and budget.
- Credentials and secrets are never committed to the repository.

## Delivery Milestones

Business outcomes in order. There are no dates (the plan is not time-boxed); each milestone gets a detailed TDD plan when it starts.

| # | Milestone | Outcome | Status | Plan |
|---|---|---|---|---|
| 0 | Platform proven | Manual API calls create a paused campaign in a sandbox account | pending | `.claude/plans/00-implementation-roadmap.md` §M0 |
| 1 | Foundation | Users can sign up and log in; every action is audit-logged | pending | `.claude/plans/01-foundation.plan.md` |
| 2 | Safe agent core | The workflow refuses illegal steps and invalid AI output; approval is enforced | pending | `.claude/plans/02-harness-core.plan.md` |
| 3 | Meta connected | Users connect their ad account and Page through Meta login | pending | roadmap §M3 |
| 4 | Brief to proposal | A chat produces a validated campaign proposal | pending | roadmap §M4 |
| 5 | Review and approve | Users revise, compare versions and approve | pending | roadmap §M5 |
| 6 | Published | Approved campaigns appear on Meta paused; activation and recovery work | pending | roadmap §M6 |
| 7 | Monitored | Metrics are collected and charted over time | pending | roadmap §M7 |
| 8 | Explained and improved | Reports and approved improvements work end to end | pending | roadmap §M8 |
| 9 | Proven | Evaluation suites pass; live model evaluation recorded | pending | roadmap §M9 |
| 10 | Shipped | Deployed, documented, demo recorded | pending | roadmap §M10 |

## Open Questions

- [ ] Will a small real-budget run (₹100–200/day for 2–3 days) be approved to show real metrics in the demo?
- [ ] Does Meta v26 require an explicit Advantage+ audience setting on ad sets for our setup? (Doc 1 §6.2)
- [ ] Which Page permission does ad creation require for our app type? (Doc 1 §6.2)
- [ ] Does the live model evaluation confirm the provisional model choice? (Doc 3 §6)
- [ ] Does the chosen MongoDB Atlas tier allow custom database roles (for the append-only audit log)?
- [ ] Should awareness campaigns be in the MVP, or traffic only?
- [ ] Can a sandbox ad account create Instagram creatives (`instagram_user_id`)? (Doc 1 §6.8)

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Sandbox gives no real metrics | Certain | Medium | Labelled simulation; optional small real run |
| Meta API behaviour differs from docs | Medium | High | Milestone 0 proves every call before code depends on it |
| Meta API version expires during the project | Low | High | Version is configuration; changelog check |
| AI output breaks copy rules or invents targeting | Medium | Medium | Validation and repair; targeting must resolve to real platform IDs |
| Prompt injection attempts | Medium | High | AI has no ability to publish or spend; approval only through the authenticated UI |
| Token expiry mid-demo | Low | Medium | Expiry warning; reconnect flow |
| Solo builder, broad scope | High | High | Strict milestone order; core flow before extras |

---
*Status: DRAFT — requirements only. Implementation planning: `.claude/plans/00-implementation-roadmap.md`.*
