# Implementation & Test Report: Reliable Images and Live DM Agent

Date: 23 October 2026  
Target Branch: `feat/dm-agent-organic-posts`  
Repository: `https://github.com/14himaja/ad_campaign_manager/`

---

## 1. Summary of Completed Implementation

### Part A: Reliable Images (A1 - A6)
- **A1. Dedicated Duplicate Endpoint**: `POST /v1/campaigns/{id}/duplicate` resets publish status and Meta identifiers while preserving `image_id` and image URL without re-upload or re-generation.
- **A2. Production Tunnel Stability**: Configured for Next.js production server execution to prevent chunk loading errors over ngrok/localtunnel.
- **A3. Read-only Published Campaigns**: Published and paused campaigns are locked against accidental edits or duplicate creates, directing the owner to duplicate first.
- **A4. GridFS Media Library & Reusability**: Reusable image catalog with GridFS storage and owner-scoped access (`GET /images/{id}`, `GET /media`, `PUT /campaigns/{id}/image`).
- **A5. Image Format Invariants**: Strict normalization to 1080x1080 JPEG for Instagram compatibility (center cropping 4:5 / 1:1, rejecting files < 600px wide or non-image assets).
- **A6. Resilient Image UI**: `<AdImage>` component with fallback placeholder and token-expiration states.

### Part B: DM Agent (B1 - B6)
- **B1. Real Instagram DM Support & Routing**:
  - Webhook parser in `app/api/webhooks.py` extracts messages from both `entry[].messaging[]` and `entry[].changes[]` (`field == "messages"`).
  - Recipient connection lookup supports both `instagram_user_id` and Facebook `page_id` (`{"$or": [{"instagram_user_id": recipient_id}, {"page_id": recipient_id}], "status": "ACTIVE"}`).
  - `send_dm` in `app/meta/sdk_gateway.py` handles both `message_id` and `id` return structures from `/{page_id}/messages`.
- **B2. Webhook Observability & Status**:
  - `GET /dm/status` provides real-time health: `agent_enabled`, `webhook_verified`, `webhook_subscribed`, `subscribed_pages`, `last_inbound_at`, `last_error`.
  - Non-production audit logging for incoming webhooks (`WEBHOOK_RAW`). Structured logging redacts raw customer message text.
- **B3. Alerting & Triage**:
  - Sidebar badge `DM Agent (N)` tracks threads in `NEEDS_HUMAN` status via 30s polling.
  - Thread lists sort `NEEDS_HUMAN` first. 24-hour reply window enforcement with `OUTSIDE_MESSAGING_WINDOW` rejection.
- **B4. Non-Text & Event Handling**:
  - Non-text messages receive an automatic polite reply: *"I can read text only. Please type your question."* and flag `NEEDS_HUMAN`.
  - Reactions (`[reaction: ❤️]`), story mentions (`[story mention]`), and story replies are stored in the thread history without trigger errors or auto-replies.
- **B5. Safety, Privacy & Quotas**:
  - Strict HMAC SHA-256 signature enforcement (`X-Hub-Signature-256`), rejecting missing or mismatched secrets with 403.
  - Prompt injection defense: customer text and knowledge block wrapped in strict data boundaries with anti-jailbreak directives.
  - `dm_seen` TTL index (7 days / 604,800s) prevents unbounded collection growth.
  - Thread message history capped at 100 messages. Owner deletion endpoint `DELETE /dm/threads/{id}`.
  - Rate limiting (1 reply per 3 seconds, 30 bot-eligible replies per hour) handing off to `NEEDS_HUMAN` on bursts.
  - Token tracking in `DM_REPLIED` audit log.
- **B6. Knowledge Block UI Guidance**:
  - Example knowledge card with 1-click *"Use this example"* insertion.
  - Live character counter with 6,000 character limit enforcement and warnings.

---

## 2. Test Verification Matrix

### 2.1 Section 5.1 Images Test Suite

| Test Requirement | Test Implementation | Result |
|---|---|---|
| Duplicate a published ad | `backend/tests/api/test_campaigns_api.py::test_duplicate_published_campaign_preserves_image_but_not_meta_state` | **PASS** |
| Open and close a published ad in studio | `frontend/components/CampaignStudioModal.test.tsx` ("opens a non-draft ad read-only") | **PASS** |
| Studio on a DRAFT, edit title, save | `frontend/components/CampaignStudioModal.test.tsx` ("saves edits with PUT when moving to the next step") | **PASS** |
| Image list with two users | `backend/tests/api/test_images_api.py::test_images_are_private_to_their_owner` | **PASS** |
| `GET /images/{id}` as another user | `backend/tests/api/test_images_api.py::test_images_are_private_to_their_owner` (404) | **PASS** |
| `GET /images/{id}` without a session | `backend/tests/api/test_images_api.py::test_image_route_requires_a_session` (401) | **PASS** |
| Delete campaign sharing image | `backend/tests/api/test_images_api.py::test_deleting_campaign_keeps_image_shared_with_another_campaign` | **PASS** |
| Upload PNG, non-square JPEG, 200x200 | `backend/tests/api/test_images_api.py::test_upload_converts_a_non_square_jpeg_and_rejects_a_small_image` | **PASS** |
| `<AdImage>` with failing request | `frontend/components/AdImage.test.tsx` ("shows a clear fallback when the request fails") | **PASS** |
| Signed public URL: bad sig / wrong id | `backend/tests/api/test_organic_api.py::test_instagram_can_fetch_the_image_only_with_the_signature` | **PASS** |

### 2.2 Section 5.2 DM Agent Test Suite

| Test Requirement | Test Implementation | Result |
|---|---|---|
| GET handshake with right / wrong token | `backend/tests/api/test_dm_api.py::test_webhook_handshake_returns_the_challenge` | **PASS** |
| POST with no / wrong / right signature | `backend/tests/api/test_dm_api.py::test_unsigned_or_wrongly_signed_delivery_is_rejected` | **PASS** |
| Text DM, agent on, answer in block | `backend/tests/api/test_dm_api.py::test_inbound_dm_gets_an_answer_from_the_knowledge_block` | **PASS** |
| Same message id delivered twice | `backend/tests/api/test_dm_api.py::test_redelivered_message_is_answered_once` | **PASS** |
| Question not in block | `backend/tests/api/test_dm_api.py::test_when_the_ai_needs_a_human_the_handoff_goes_out_and_the_bot_stops` | **PASS** |
| Customer angry or asks for a human | `backend/tests/api/test_dm_api.py::test_customer_angry_or_asks_for_a_human_hands_over` | **PASS** |
| AI raises (bad key, quota, invalid JSON) | `backend/tests/api/test_dm_api.py::test_any_ai_failure_hands_over_instead_of_going_silent` | **PASS** |
| Meta send fails (`MetaError`) | `backend/tests/api/test_dm_api.py::test_meta_send_failure_flags_the_thread_for_a_human` | **PASS** |
| Message older than 24 hours | `backend/tests/api/test_dm_api.py::test_nothing_is_sent_outside_the_24_hour_window` | **PASS** |
| Photo-only message | `backend/tests/api/test_dm_api.py::test_photo_only_message_gets_polite_text_reply` | **PASS** |
| Echo of our own message (`is_echo`) | `backend/tests/api/test_dm_api.py::test_echoes_and_unknown_accounts_are_ignored` | **PASS** |
| Admin replies from UI after 24 hours | `backend/tests/api/test_dm_api.py::test_manual_reply_is_refused_after_24_hours` | **PASS** |
| Admin replies, then "hand back to bot" | `backend/tests/api/test_dm_api.py::test_owner_can_reply_by_hand_then_hand_the_thread_back` | **PASS** |
| Prompt injection in customer text/block | `backend/tests/agents/test_dm_agent.py::test_prompt_injection_in_customer_or_knowledge_is_treated_as_data` | **PASS** |
| Agent off | `backend/tests/api/test_dm_api.py::test_disabled_agent_records_the_message_but_does_not_answer` | **PASS** |
| Two users, same customer id | `backend/tests/api/test_dm_api.py::test_two_users_same_customer_id_threads_do_not_mix` | **PASS** |

---

## 3. Automated Quality Gate Results

| Check | Command | Status | Details |
|---|---|---|---|
| Python Linter | `uv run ruff check scripts app tests` | **GREEN** | All checks passed. Zero violations. |
| Python Test Suite | `uv run pytest -q` | **GREEN** | 574 passed, 11 skipped (standalone mongod transaction tests excluded). |
| TypeScript Compiler | `npx tsc --noEmit` | **GREEN** | Exited 0 with zero type errors. |
| Frontend Linter | `npx eslint .` | **GREEN** | Zero errors, zero warnings. |
| Vitest Unit Suite | `npx vitest run` | **GREEN** | 19 test files passed (99 tests total). |

---

## 4. Simulated Webhook Tool (`signed_post.py`)

A standalone simulation utility is available at `scripts/signed_post.py`. It constructs an authentic Meta HMAC SHA-256 signed POST request to `/webhooks/instagram` without needing real Instagram connectivity.

```powershell
python scripts/signed_post.py <META_APP_SECRET> <instagram_user_id> "What time do you open?"
```

In `META_MODE=fake`, the reply is recorded in memory and audit logged. In `META_MODE=real`, it attempts delivery to the customer ID or tests error handling.

---

## 5. Notes on B1 "Known Unknowns"

1. **Payload Structure (`messaging` vs `changes`)**:
   - Meta webhooks deliver direct messages either under `entry[].messaging[]` (classic Instagram Messaging) or `entry[].changes[]` with `field: "messages"` (Graph API subscription).
   - Solution: Normalized parser in `backend/app/api/webhooks.py` extracts events from both payload formats transparently.
2. **Recipient Identifier Resolution**:
   - Webhook events can supply either the Instagram account ID or the associated Facebook Page ID in `recipient.id`.
   - Solution: DB lookup matches either identifier (`{"$or": [{"instagram_user_id": id}, {"page_id": id}], "status": "ACTIVE"}`).
3. **Outbound Send Edge & Response Body**:
   - Sending DMs uses `POST /{page_id}/messages` with `recipient={"id": customer_id}`.
   - Meta can return `{"message_id": "mid..."}` or `{"id": "mid..."}`. Gateway safely parses both.
