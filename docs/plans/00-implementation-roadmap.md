# Ad Campaign Manager — Implementation Roadmap (TDD)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement each milestone plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Every code task follows superpowers:test-driven-development.

**Goal:** Build the AI-powered **Instagram** ad campaign manager from the PRD as a working, deployed prototype, test-first.

**Architecture:** One FastAPI service + MongoDB + a Next.js frontend. Each chat turn runs a **Google ADK 2.x `Workflow`**: small agents do the language work, and deterministic function nodes call our domain services. Approvals, publishing and live changes are plain backend services that no agent can reach. Meta is accessed through the **official `facebook-business` SDK** behind `AdsReader` / `AdsWriter` interfaces, with an in-memory `FakeAdsGateway` for tests and mock mode.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, google-adk 2.x (+ LiteLLM), facebook-business 26.x, tenacity, PyMongo async, APScheduler, Pillow; Next.js + TypeScript; pytest, Vitest, Playwright. Full list and principles: `tech-stack.md`.

**Spec:** `.claude/prds/ad-campaign-manager.prd.md` (what), `High-Level Design — Ad Campaign Manager.md` (architecture), `.claude/plans/lld.md` (names, signatures, algorithms).

**Builder:** one developer. **Timeline:** not time-boxed; milestones run in order, and a milestone is done only when its exit criteria pass.

## Global Constraints

- Graph API version from `META_API_VERSION` (default `v26.0`); `facebook-business` 26.x; never hard-code versions in code.
- Ads run on **Instagram only**: `publisher_platforms=["instagram"]`, positions from `INSTAGRAM_POSITIONS` (default `stream,explore`); creatives use `instagram_user_id`.
- Copy limits: headline ≤ 40, primary text (caption) ≤ 125, description ≤ 30; 2–3 variants; CTA ∈ `LEARN_MORE, SIGN_UP, DOWNLOAD, GET_QUOTE, CONTACT_US, SUBSCRIBE`.
- Images: JPG/PNG, ≤ 8 MB, width ≥ 600 px, width/height between 0.8 and 1.91.
- Every Meta object is created `PAUSED`; ACTIVE only through the activate endpoint with an `ACTIVATE` approval.
- **Agent tools receive `AdsReader` only.** `AdsWriter` is used only by `meta/publisher.py` and `optimization/apply.py`.
- Budgets are integer minor units; no floats for money. All timestamps UTC and timezone-aware, from an injected `Clock`.
- `domain/` has no I/O and imports nothing from `pymongo`, `httpx`, `facebook_business`, `google.adk`, `litellm`.
- Error responses use `{"error": {"code", "message", "details"}}`.
- Tests that touch MongoDB use a real replica set and a per-test database.
- Secrets only in env vars; `.env` git-ignored.

---

## How We Do TDD Here

### The cycle (every task, every milestone)

1. **RED:** write one failing test for one behaviour. Before writing it, say which production change would make it fail.
2. **Verify RED:** run it. It must fail because the feature is missing, not because of a typo. Note the failure line.
3. **GREEN:** write the least code that passes. No extra options.
4. **Verify GREEN:** run the file, then the whole suite. Output must be clean.
5. **REFACTOR:** only while green; no new behaviour.
6. **Commit:** one commit per task, suite green.

Exceptions (agreed): config files, lockfiles, and Milestone 0 manual exploration. Exploration code is thrown away, never copied into `app/`.

### Outside-in: the full process is mocked and tested from Milestone 4

`tests/e2e/test_full_lifecycle.py` drives the **real FastAPI app over HTTP** through the whole product flow (HLD steps 1–16), with fakes only at the outer boundaries. It grows one segment per milestone:

| Milestone | Segment added (written first, RED, at milestone start) | Green when |
|---|---|---|
| M4 | register → connect (fake) → brief → question → answer → image → proposal v1 | M4 exit |
| M5 | feedback → v2 + diff → approve (and: stale approve rejected) | M5 exit |
| M6 | publish (paused objects in the fake) → activate | M6 exit |
| M7 | advance clock 7 days → insights collected (simulated, labelled) | M7 exit |
| M8 | report (4 item types, grounded) → proposal → approve → applied | M8 exit — **whole process green** |

Each milestone starts by adding its segment (watch it fail), then unit and integration tests drive the code, and the milestone ends when the segment passes.

### What is faked, and why

| Boundary | In tests | Why this and not something else |
|---|---|---|
| LLM | `ScriptedModel` (an ADK `BaseLlm` subclass) answering from a scenario JSON per agent | Deterministic, free, offline. It goes through the real ADK runner, workflow, callbacks and output_schema parsing, so we test our real agent wiring, not a mock of it |
| Meta / Instagram | `FakeAdsGateway` (in-memory Meta) | The whole process can publish and "deliver" without Meta. A **shared contract test suite** proves it behaves like `MetaSdkGateway` |
| Time | `FixedClock` | "7 days later", token expiry and campaign end dates become instant and repeatable |
| MongoDB | **Real** (Docker replica set, a fresh database per test) | Unique indexes, conditional updates and transactions are what we rely on; mocks get exactly these wrong |
| HTTP of the Meta SDK | `responses` (only inside the SDK gateway's contract tests) | Proves our mapping of real Meta payloads (from Milestone 0) and errors |

Rule: **we never mock our own code.** Fakes replace things we don't own (LLM provider, Meta, the clock), and each fake is proven by a contract test or by running through the real framework.

### Commands

```bash
docker compose up -d mongo                         # MongoDB replica set rs0
cd backend && uv run pytest -q                     # whole backend suite
cd backend && uv run pytest tests/unit/test_x.py::test_y -v
cd backend && uv run pytest tests/e2e -q           # the mocked full process
cd backend && uv run ruff check . && uv run ruff format --check .
cd frontend && npm test && npx playwright test     # Playwright runs the app in mock mode
```

---

## Milestone Map

| # | Milestone | Detailed plan | Depends on | Exit criteria |
|---|---|---|---|---|
| M0 | Meta + Instagram proven by hand | §M0 below | — | Saved payloads for every call; open items resolved |
| M1 | Foundation | `01-foundation.plan.md` | — | Register/login, audit, correlation IDs, encryption, CI green |
| M2 | Harness core + ADK spike | `02-harness-core.plan.md` | M1 | Domain, state machine, versions, approvals, ADK spike, ScriptedModel, tool guard, repair-loop workflow |
| M3 | Meta connection + gateway | `03-meta-gateway.plan.md` | M0, M1 | OAuth works against the sandbox; contract suite green for fake and SDK gateways |
| M4 | Brief → proposal (ADK agents) | `04-06-brief-review-publish.plan.md` | M2, M3 | Lifecycle segment 1 green; one real-model run produces v1 |
| M5 | Review + approval | `04-06-brief-review-publish.plan.md` | M4 | Segment 2 green; approval-gate tests 100% |
| M6 | Publishing | `04-06-brief-review-publish.plan.md` | M5 | Segment 3 green; paused campaign visible in sandbox Ads Manager |
| M7 | Monitoring | written at M7 start | M6 | Segment 4 green |
| M8 | Analysis + optimization | written at M8 start | M7 | Segment 5 green — full process passes offline |
| M9 | Evaluation | written at M9 start | M8 | Failure-variant E2E tests + ADK eval sets + live model eval recorded |
| M10 | Ship | written at M10 start | M9 | Deployed; 4 demo scenarios reproducible; docs and video done |

**Why later detailed plans are written at milestone start:** a detailed plan contains full test and implementation code, which depends on the exact interfaces the previous milestone produced. The scope of each milestone (tasks + RED tests) is fixed below, so it won't drift. When a milestone starts, write its plan in the same format as `01` and `02` (superpowers:writing-plans) and link it here.

---

## M0 — Meta + Instagram Proven by Hand

### Learn this phase

**What happens:** before writing any code, you prove with Meta's own tool (Graph API Explorer) that every call our app needs works on **v26.0**, and you save the exact requests and responses. Those files become the contract our code and tests are built against.

**Concepts:**
- **Graph API:** every Meta object (ad account `act_123`, campaign, ad set, ad, Page) has an id. You `GET` it to read, `POST` to it to update, and `POST` to its *edges* (e.g. `act_123/campaigns`) to create children.
- **Object hierarchy:** Ad account → Campaign (objective) → Ad set (budget, schedule, targeting **including the Instagram placement**) → Ad, which points to an Ad creative (image, caption, CTA and the **Instagram account** it runs as).
- **Tokens:** Explorer gives you a short-lived user token with the scopes you tick. The app will later get the same through OAuth.
- **Sandbox ad account:** accepts every call but never delivers ads, so insights come back empty.

**How to do it:** follow the checklist and save each request/response pair as JSON in `docs/meta-payloads/` (for example `p2_create_campaign.request.json` and `p2_create_campaign.response.json`).

**Pitfalls:**
- Creating a campaign without `is_adset_budget_sharing_enabled` fails in v26. Save that error too; it becomes a test fixture.
- Targeting needs interest **ids** from the search call, not names.
- The creative needs both `page_id` and `instagram_user_id`.

### Checklist

- [ ] Meta developer app (Business use case) + Marketing API product (Doc 1 §8).
- [ ] Sandbox ad account; test Facebook Page; **Instagram professional account linked to the Page**.
- [ ] Explorer on `v26.0` with `ads_management, ads_read, pages_show_list, instagram_basic` (+ any Page permission requested). Save request/response for:
  - [ ] `GET me/adaccounts?fields=account_id,account_status,currency,min_daily_budget`
  - [ ] `GET me/accounts`
  - [ ] `GET {page_id}?fields=instagram_business_account{id,username}`
  - [ ] `GET search?type=adinterest&q=python`
  - [ ] `GET search?type=adgeolocation&q=Bengaluru`
  - [ ] `GET act_<id>/delivery_estimate` (targeting with `publisher_platforms=["instagram"]`)
  - [ ] `POST act_<id>/adimages` (a 1080×1080 JPG)
  - [ ] `POST act_<id>/campaigns`: first without `is_adset_budget_sharing_enabled` (save the error), then with it
  - [ ] `POST act_<id>/adsets` (lifetime budget, start/end, interest ids, `publisher_platforms=["instagram"]`, `instagram_positions=["stream","explore"]`). Note whether an Advantage+ audience flag is required
  - [ ] `POST act_<id>/adcreatives` with `object_story_spec.page_id` + `instagram_user_id` + `link_data`
  - [ ] `POST act_<id>/ads` (PAUSED)
  - [ ] `GET act_<id>/adsets?filtering=[{"field":"name","operator":"EQUAL","value":"<name>"}]`
  - [ ] `POST <ad_id>` `status=ACTIVE`, then `GET <ad_id>?fields=effective_status`
  - [ ] `GET <campaign_id>/insights?level=ad&time_increment=1` (expect empty)
  - [ ] `DELETE <ad_id>`
- [ ] Save the response headers of one call (`X-Business-Use-Case-Usage`, `X-App-Usage`).
- [ ] Update Doc 1 (§6.2, §6.8): resolve every **[To verify in Phase 1]** item.
- [ ] Commit `docs: add verified Meta v26 Instagram payloads`.

---

## M1 — Foundation → `01-foundation.plan.md`

Learn-this-phase notes are inside the plan. Tasks: project tooling + settings · MongoDB + indexes + per-test database + app factory · correlation IDs + audit log · passwords + JWT · error envelope + auth API + rate limiter · token encryption · Clock · CI.

## M2 — Harness Core + ADK Spike → `02-harness-core.plan.md`

Learn-this-phase notes are inside the plan. Tasks: copy rules + Instagram image check · requirements · state table · conditional transitions · versions · approvals (transaction) · **ADK spike** · ScriptedModel · tool guard + model logger · validate→repair workflow proven with ScriptedModel.

---

## M3 — Meta Connection + Gateway

### Learn this phase

**What happens:** the user clicks "Connect Instagram ads". Meta's login asks them to grant our app access. We get a code, exchange it for a token (short-lived, then ~60-day), encrypt it, and store it. Then we list their ad accounts, Pages, and the Instagram account linked to each Page, and they pick one.

**Concepts:**
- **OAuth authorization-code flow:** redirect to Meta → user consents → Meta redirects back with `code` + our `state` → server exchanges `code` for a token. The `state` is a signed, short-lived value we generated, which stops cross-site request forgery.
- **Ports and adapters:** our code talks to two small interfaces (`AdsReader`, `AdsWriter`). `MetaSdkGateway` implements them with the official SDK; `FakeAdsGateway` implements them in memory.
- **Contract tests:** one test suite, run against both gateways. If the fake passes the same tests as the real one, everything built on the fake can be trusted (Liskov substitution).
- **Why the SDK:** it already handles `appsecret_proof`, paging and Meta's error format. We only translate its calls and errors into our interface. It is synchronous, so the gateway runs calls with `asyncio.to_thread`.

**How to implement:**
1. Write the contract tests first against the fake (they fail), then build `FakeAdsGateway`.
2. Point the same tests at `MetaSdkGateway`, with HTTP mocked by `responses` using the M0 payloads, and implement the gateway until they pass.
3. Add OAuth with respx-mocked token endpoints.
4. Wire the gateway into `container.py`.

**Mocks used:** `responses` (SDK HTTP), respx (OAuth HTTP), `FakeAdsGateway`.

**Pitfalls:**
- Never call `FacebookAdsApi.init()`, because it is global. Build one API object per user connection.
- Never log tokens.
- Write calls (`create`) are **not** retried inside the gateway; the publisher decides (M6).

| Task | RED tests (write first, watch fail) | Module (LLD) |
|---|---|---|
| 3.1 Error mapping | `test_throttle_codes_are_retryable` (4, 17, 613, 80004) · `test_190_is_auth` · `test_100_is_invalid_and_keeps_subcode` · `test_unknown_code_is_unknown` · `test_is_retryable_predicate_matches_table` | `meta/errors.py` |
| 3.2 Ports + contract suite | `tests/contract/test_ads_gateway_contract.py` parametrised over gateways: `create_returns_id` · `find_by_name_finds_created` · `find_by_name_none_when_absent` · `update_status` · `delete_removes` · `search_interests_returns_options` · `error_code_100_raises_invalid` | `meta/ports.py` |
| 3.3 FakeAdsGateway | contract suite (fake) + `test_fail_at_raises_configured_error` · `test_timeout_after_create_creates_then_raises` · `test_activated_ad_goes_pending_review_then_active` · `test_insights_only_for_active_days_up_to_clock` | `meta/fake.py` |
| 3.4 MetaSdkGateway | contract suite (SDK + `responses` with M0 payloads) + `test_uses_per_connection_api_not_global` · `test_appsecret_proof_present_in_requests` · `test_read_retried_on_17_then_succeeds` · `test_create_not_retried` · `test_token_never_logged` | `meta/sdk_gateway.py` |
| 3.5 Payload builders | `test_campaign_payload_matches_m0` · `test_adset_payload_has_instagram_platform_and_positions` · `test_creative_payload_has_page_and_instagram_user_id` · `test_object_name_deterministic` | `meta/payloads.py` |
| 3.6 OAuth | `test_auth_url_has_scopes_state_version` · respx `test_code_exchanged_then_long_lived_with_expiry` · API `test_callback_rejects_bad_state` · `test_token_stored_encrypted` · `test_fake_mode_connect_creates_fake_connection` | `meta/oauth.py`, `api/meta_oauth.py` |
| 3.7 Assets + selection | `test_assets_include_instagram_account_per_page` · `test_connection_rejected_when_page_has_no_instagram` | `api/meta_oauth.py` |
| 3.8 Container wiring | `test_container_uses_fake_in_fake_mode` · `test_fake_mode_refused_in_production` | `container.py` |
| 3.9 UI | Vitest `MetaConnectCard shows Instagram account and expiry warning` | `/settings/meta` |

Exit: a real connect against the sandbox app stores an encrypted token, and `GET /meta/assets` shows the sandbox account, the Page and its Instagram account. (Completed & Verified: all contract, unit, integration, and frontend suites passing).

## M4 — Brief → Proposal (ADK Agents, steps 1–7)

### Learn this phase

**What happens:** the user types a brief. One ADK `Workflow` run handles the turn:
1. Route by campaign state → the **extract agent** turns text into fields.
2. A **function node** validates them and decides: ask, or plan?
3. If something is missing, the **ask agent** writes the question.
4. When everything is there, the **research agent** calls the search tools (real Meta interest ids, audience size).
5. The **plan agent** picks objective and interests. A function node builds the plan and **keeps only ids the tools actually returned**.
6. The **creative agent** writes 2–3 Instagram ads, and a function node validates them. On failure it routes back to the agent with the exact errors, at most twice.
7. A function node saves version 1.

**Concepts:**
- **Agent** = model + instruction + (`output_schema` or `tools`). One job each.
- **Function node** = plain Python in the graph. This is where the harness decides; the model never does.
- **Routes** = `Event(route="...")` from a node picks the next edge, like a switch statement.
- **`output_schema`** makes the agent return JSON matching a Pydantic model. Lengths are still checked by our node.
- **Tool guard** (`before_tool_callback`) runs before every tool call: is this tool allowed in this state, and are the arguments valid? Returning a dict blocks the call.
- **Session state** is per turn; MongoDB holds everything durable. The instruction's `{campaign_state}` placeholder is filled from the seeded state.
- **Untrusted text** (user messages, landing page) is wrapped in `<untrusted_data>`, and the instructions say never to follow instructions found there.

**How to implement:**
1. Add lifecycle segment 1 (RED).
2. Build instructions (rendered from `rules.py`), the research tools, the agents factory, the nodes (each unit-tested by calling it directly with a `TurnDeps`), the workflow (tested with ScriptedModel scenarios), and `AgentRuntime.run_turn`.
3. Finish with the chat endpoint.

**Mocks used:** ScriptedModel scenarios (`brief_complete.json`, `brief_missing.json`, `overlong_headline.json`, `injection_in_brief.json`), FakeAdsGateway, FixedClock.

**Pitfalls:**
- Don't put tools and `output_schema` on the same agent (that's why research and plan are separate).
- Never trust ids from model output; only ids in `deps.resolved_interests` survive.
- Callbacks do no I/O; they append to `deps`.

| Task | RED tests | Module |
|---|---|---|
| 4.0 Lifecycle segment 1 | `test_full_lifecycle` up to "proposal v1 saved" | `tests/e2e/` |
| 4.1 Context | `test_wrap_untrusted_strips_closing_tag` · `test_seed_state_wraps_user_values` · `test_only_last_8_turns` | `agents/context.py` |
| 4.2 Instructions | `test_instructions_render_limits_from_rules` · `test_every_agent_has_prompt_version` · `test_instructions_contain_untrusted_rule_and_no_approval_power` | `agents/instructions.py` |
| 4.3 Research tools | `test_search_interests_records_resolved_ids` · `test_estimate_audience_builds_targeting_in_code_with_instagram` · `test_fetch_landing_page_has_no_url_param` · `test_fetch_landing_page_blocks_private_redirect` · `test_tools_never_get_writer` (architecture) | `agents/tools.py` |
| 4.4 Agents factory | `test_research_has_tools_and_guard_no_schema` · `test_plan_has_schema_no_tools` · `test_models_come_from_make_model` | `agents/definitions.py` |
| 4.5 Nodes | `test_route_by_state` (each state) · `test_apply_extraction_asks_when_missing` · `test_apply_extraction_moves_to_planning_when_ready` · `test_build_plan_drops_unresolved_ids` · `test_validate_assets_routes_repair_then_failed` · `test_save_version_transitions_to_in_review` | `agents/nodes.py` |
| 4.6 Turn workflow | ScriptedModel: `test_incomplete_brief_returns_question` · `test_complete_brief_produces_v1` · `test_overlong_headline_repaired` · `test_three_bad_outputs_fail_back_to_collecting` · `test_injection_brief_cannot_call_disallowed_tool` | `agents/workflows.py` |
| 4.7 Runtime | `test_run_turn_flushes_audit_and_agent_runs` · `test_model_unavailable_maps_to_503_state_unchanged` | `agents/runtime.py` |
| 4.8 Chat + image API | `test_post_message_reply_status_missing` · `test_other_users_campaign_404` · `test_message_rate_limited` · `test_image_upload_rejects_bad_ratio_422` · `test_image_upload_sets_image_id` | `api/campaigns.py` |
| 4.9 UI | Vitest `ChatPanel disables while sending` · `VariantCard renders Instagram preview with truncated caption` · `FieldStatusList confirm only for proposed` | components |

Exit: segment 1 green. One manual run with the real model (`LLM_PROVIDER=litellm`) produces a valid version 1.

## M5 — Review + Approval (steps 8–9)

### Learn this phase

**What happens:**
- A user's feedback runs the **revise agent** (same validate→repair loop) and saves version 2. The UI shows a field-by-field diff.
- On **Approve**, the browser sends the version number and the hash of what it displayed. The server checks, in one database transaction, that this is still the current version and its hash matches, records the approval, and moves the campaign to APPROVED.
- Any later edit creates a new version, which automatically revokes the approval.

**Concepts:**
- **Content hash** = fingerprint of a version. If it changed, the user didn't approve *this*.
- **Transaction** = the approval record and the state change both happen, or neither does.
- Chat text like "approve it" is just text: the only door to approval is the authenticated endpoint.

**Mocks used:** ScriptedModel (`revise_headline.json`, `approve_in_chat.json`), FakeAdsGateway.

**Pitfalls:**
- Audit the *rejected* approval outside the transaction, or the rollback erases the record.

| Task | RED tests | Module |
|---|---|---|
| 5.0 Segment 2 | lifecycle: feedback → v2 → diff → approve; stale approve → 409 | e2e |
| 5.1 Revision | `test_feedback_changes_only_requested_field` · `test_revising_approved_campaign_revokes_approval` | workflow, nodes |
| 5.2 Versions API | `test_list_versions` · `test_diff_endpoint_paths` | `api/campaigns.py` |
| 5.3 Approve API | `test_approve_matching_hash` · `test_stale_hash_409` · `test_wrong_state_409` · `test_double_approve_one_record` · `test_chat_approve_text_changes_nothing` | api, services |
| 5.4 UI | Vitest `ApprovalDialog shows account, Page, Instagram account, budget, dates, ads, hash` · `Confirm disabled until checkbox` · `VersionDiff renders` | components |

Exit: segment 2 green; approval-gate tests pass 100%.

## M6 — Publishing (steps 10–11)

### Learn this phase

**What happens:**
- After approval a background job creates, in order, the image → campaign → ad set (with Instagram placement) → one creative and one ad per variant, **all paused**.
- After each step it saves the Meta id (a checkpoint). If a call times out, it first asks Meta "does an object with this exact name exist?" and adopts it instead of creating a duplicate.
- On a hard error it stops, shows Meta's message, and offers Resume (continue from the failed step) or Discard (delete what was created).
- **Activate** is a second, separate approval.

**Concepts:**
- **Idempotency:** running the same step twice must not create two objects. Meta has no idempotency key, so deterministic names + lookup provide one.
- **Retry only what's safe:** network blips and throttling are retried (tenacity, with backoff and jitter); "invalid parameter" never is.
- **Checkpointing:** progress lives in the `publish_runs` document, so a restart can resume.

**Mocks used:** FakeAdsGateway with `fail_at` (`"ADSET": "timeout_after_create"`, `MetaError(code=100)`, `MetaError(code=190)`), FixedClock.

**Pitfalls:**
- Build payloads from the **approved version document**, never from the request or the model.

| Task | RED tests | Module |
|---|---|---|
| 6.0 Segment 3 | lifecycle: approve → publish (paused objects in fake) → activate | e2e |
| 6.1 Start | `test_requires_active_publish_approval` · `test_run_document_has_all_steps_pending` · `test_second_start_publish_in_progress` | `meta/publisher.py` |
| 6.2 Steps | `test_happy_path_all_paused_then_ready_paused` · `test_payloads_from_approved_version` · `test_checkpoint_before_next_step` | publisher |
| 6.3 Failures | `test_timeout_after_create_adopts_no_duplicate` · `test_retryable_retried_then_ok` · `test_code_100_stops_with_user_msg` · `test_code_190_stops_and_expires_connection` | publisher |
| 6.4 Resume / discard | `test_resume_from_first_unfinished` · `test_discard_deletes_reverse_and_back_to_review` | publisher |
| 6.5 Recovery | `test_startup_marks_running_runs_failed` | publisher, scheduler |
| 6.6 Activate | `test_activate_requires_activation_approval` · `test_activate_sets_all_active` · `test_activate_retry_safe` | publisher, api |
| 6.7 UI | Vitest `PublishProgress shows Resume/Discard with Meta message` · `ActivateDialog warns about spend` | components |

Exit: segment 3 green. Against the **real sandbox**, an approved campaign appears paused in Ads Manager with Instagram placements (or the documented sandbox limitation from M0 applies).

## M7 — Monitoring (step 12)

### Learn this phase

**What happens:** every 6 hours a scheduler job asks Meta for each active campaign's per-ad daily numbers for the last 3 days (Meta revises recent days) and **upserts** them, so the same day never appears twice. It also checks each ad's review status. In the sandbox there are no real numbers, so the simulator writes realistic rows marked `is_simulated`, and the UI shows a badge.

**Concepts:**
- **Upsert** with a unique key (object, level, day) makes collection safe to repeat.
- **Money as integers:** Meta returns `"123.45"`; we store `12345` paise using `Decimal`, never `float`.
- **Reach can't be summed** across days.
- **Injected clock** lets a test say "7 days later".

**Mocks used:** FakeAdsGateway (insights generated by the same simulator), FixedClock.

| Task | RED tests | Module |
|---|---|---|
| 7.0 Segment 4 | lifecycle: advance 7 days → collect → insights endpoint shows rows + simulated flag | e2e |
| 7.1 Parse | `test_spend_string_to_minor_units_without_float` · `test_missing_numbers_zero` · `test_day_stored_as_utc_midnight` | `analytics/collector.py` |
| 7.2 Collect | `test_upserts_last_3_days` · `test_twice_no_duplicates` · `test_revised_numbers_overwrite` | collector |
| 7.3 Simulator | `test_rows_marked_simulated` · `test_deterministic_for_same_seed` · `test_used_only_when_mock_metrics_and_empty` | `analytics/simulator.py` |
| 7.4 Status | `test_disapproved_status_and_reason_saved` | collector |
| 7.5 Scheduler | `test_job_continues_after_one_campaign_fails` · `test_ended_campaign_completed` · `test_jobs_have_correlation_id` | `scheduler.py` |
| 7.6 API + UI | `test_insights_endpoint_rows_and_simulated` · Vitest `MetricsChart SIMULATED badge` | api, components |

Exit: segment 4 green.

## M8 — Analysis + Optimization (steps 13–16)

### Learn this phase

**What happens:**
- **Code** computes the numbers: CTR, CPC, CPM, period changes, and a two-proportion z-test between variants. It flags issues (low CTR, fatigue, pacing, disapproval) and data quality.
- The **analyst agent** (an ADK analysis workflow) turns that table into report items labelled FACT / CALCULATION / ASSUMPTION / RECOMMENDATION, and may propose one change.
- A function node checks that **every number it wrote exists in the table** (repairing up to twice). Another checks the proposal against policy (e.g. budget change ≤ 30%, never pause the last ad).
- The user approves; the change is applied through `AdsWriter` and audited with before/after values.

**Concepts:**
- **Code first, model second:** numbers must be exact and reproducible; the model only explains.
- **Grounding:** a mechanical check that the explanation doesn't invent numbers.
- **Open/Closed:** each proposal type has a handler in a dict, so adding a type doesn't change existing code.

**Mocks used:** ScriptedModel (`report_grounded.json`, `report_invented_number.json`), FakeAdsGateway, FixedClock.

| Task | RED tests | Module |
|---|---|---|
| 8.0 Segment 5 | lifecycle: report → proposal → approve → applied (**full process green**) | e2e |
| 8.1 Metrics | `test_summarize` · `test_zero_impressions_none` · `test_compare_periods` · `test_z_test_known_value` | `analytics/metrics.py` |
| 8.2 Issues | `test_low_ctr` · `test_fatigue_needs_both_signals` · `test_pacing` · `test_no_delivery_24h` | `analytics/issues.py` |
| 8.3 Grounding | `test_grounded_passes` · `test_invented_number_found` · `test_percent_and_commas_normalised` · `test_assumptions_not_checked` | `analytics/grounding.py` |
| 8.4 Analysis workflow | ScriptedModel: `test_report_has_four_types_and_range` · `test_invented_number_repaired` · `test_unrepairable_report_saved_with_warning` · `test_simulated_data_noted` | agents |
| 8.5 Policy | `test_budget_over_30_percent_blocked` · `test_above_cap_blocked` · `test_two_changes_in_24h_blocked` · `test_pause_last_ad_blocked` · `test_pause_needs_significance` | `optimization/policy.py` |
| 8.6 Apply | `test_approve_rechecks_current_values` · `test_changed_values_expire` · `test_pause_ad_applied_and_audited` · `test_new_creative_creates_review_version` | `optimization/apply.py` |
| 8.7 UI | Vitest `ReportCard text labels per type` · `ProposalCard approve needs confirm` | components |

Exit: segment 5 green — **the full product process runs offline in one test.**

## M9 — Evaluation

### Learn this phase

Two kinds of evaluation:
1. **Harness evaluation:** deterministic tests that the safety properties always hold (HLD §15.2 E1–E9). These are failure variants of the lifecycle test: injection briefs, approve-in-chat, stale hash, publish without approval, Meta errors, duplicate collection, invented numbers, policy breaches.
2. **Model evaluation:** how well the real model does on 20 briefs, using ADK's `AgentEvaluator` / `adk eval` with eval sets plus our own metrics (Doc 3 §6).

The first must be 100%; the second is measured and reported.

| Task | Deliverable |
|---|---|
| 9.1 | `tests/e2e/test_failure_scenarios.py` covering E1–E9 with scripted scenarios and `fail_at` |
| 9.2 | `evals/*.evalset.json` for the extract and creative agents; `pytest -m live_eval` runs `AgentEvaluator.evaluate(...)` |
| 9.3 | `evals/run_live_eval.py` (20 briefs → metrics table → `evals/results/<date>.md`) |
| 9.4 | Run it; fill in Doc 3 §6; confirm or change the model |

## M10 — Ship

| Task | Deliverable / check |
|---|---|
| 10.1 Security | `/cso` or `ecc:security-review`; gitleaks clean; test that every campaign route returns 404 for another user's id; cookie flags |
| 10.2 Browser E2E | Playwright against **mock mode**: the 4 demo scenarios (HLD §15.3) |
| 10.3 Deploy | Atlas (custom audit role if available), Render (always-on), Vercel rewrites, Meta redirect URI, testers added |
| 10.4 Docs | README (all sections the brief lists), architecture doc, Docs 1–3 updated with verified facts, limitations |
| 10.5 Demo video | Happy path (real sandbox where possible) + missing info + blocked publish + recovered failure (mock mode) |
| 10.6 Review | `/review` on the final diff; fix; tag `v1.0` |

---

## Definition of Done (every milestone)

- [ ] Every task followed the TDD cycle; suite green; Ruff clean.
- [ ] The milestone's lifecycle segment is green (from M4).
- [ ] Every new external action writes an audit entry (asserted in a test).
- [ ] No secrets in code, logs or fixtures.
- [ ] LLD updated if a name or signature changed.
- [ ] PRD milestone status updated; the next milestone's detailed plan written.
