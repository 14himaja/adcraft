# DM agent and organic Instagram posts

Two features on top of the ads flow. Both use the Instagram account the user already connected under
Settings > Meta Connection, so every client who connects their own account gets their own agent and their own
posts. Nothing here needs an agency-style "many clients under one login" model.

## DM agent

An inbound Instagram DM triggers Meta's webhook. The server answers only from the **knowledge block** the owner
wrote (DM Agent page in the sidebar: hours, prices, FAQs, tone, hand-over message). If the answer is not in the
block, the customer is upset, or the AI fails for any reason, the customer gets the owner's hand-over message and the
thread is flagged **Needs you**; the AI stays quiet on that thread until the owner hands it back.

- Replies are only sent within 24 hours of the customer's last message (Meta rule). The owner can also type a
  reply from the thread; that is refused after 24 hours for the same reason.
- Each webhook message id is answered once (Meta redelivers).
- The owner's text and the customer's message reach the model wrapped as data, never as instructions.
- `POST /dm/preview` (the "Try it" box) runs the model on the saved block without touching Instagram.

### Meta app setup (manual, once)

1. App > Add product > Webhooks > object **Instagram**. Callback URL `https://<your-api>/webhooks/instagram`,
   verify token = `META_WEBHOOK_VERIFY_TOKEN`. Subscribe the `messages` field.
2. Permissions: `instagram_manage_messages`, `pages_messaging`, `pages_manage_metadata`. They are already in
   `SCOPES` (`backend/app/meta/oauth.py`); with Facebook Login for Business, add them to the login configuration too.
3. Users outside the app's roles need **App Review** (Advanced Access) and Business Verification. Until then it only
   works for Instagram accounts that have a role on the app.
4. Turning the agent on in the UI subscribes the user's Page to `messages` (`POST /{page_id}/subscribed_apps`).

Existing users must reconnect Meta once so the new permissions are granted.

## Organic posts

Post to Instagram page in the sidebar: pick or generate or upload a picture, write a caption, confirm. It is a normal
feed post (Content Publishing API, `instagram_content_publish`), not an ad, and costs nothing.

- Meta downloads the image itself, so the server serves it from a signed public URL
  `PUBLIC_BASE_URL/public/images/<id>?sig=...`. The signature only works for that one image.
- The account must be a Professional (Business or Creator) account linked to a Page. Instagram accepts JPEG only;
  uploads are converted. About 50 API posts per 24 hours.
- **Which account:** the page lists every Instagram account the connected login can manage and lets you pick one
  (`GET /organic/accounts`, `instagram_user_id` on `POST /organic/posts`). Pages that cannot be used are listed with the
  reason. Posting needs no ad account to be selected.
- **Requirements for an account:** Business or Creator account, linked to a Facebook Page, managed by the connected
  Facebook login. A client who is not on your Page connects their own login, or gives your login access to the Page.
- Real posting is off until `ALLOW_ORGANIC_PUBLISH=true` (like `ALLOW_REAL_AD_SPEND`). Fake Meta mode always works.

## Settings added

| Variable | Purpose |
|---|---|
| `META_WEBHOOK_VERIFY_TOKEN` | Handshake string typed into Meta's webhook page (empty = handshake refused) |
| `META_APP_SECRET` | Also verifies the `X-Hub-Signature-256` of every delivery; unsigned posts are rejected |
| `PUBLIC_BASE_URL` | Public https origin of this API, needed for posting |
| `OPENAI_IMAGE_QUALITY` | `low`, `medium` (default), `high` or `auto`. High costs about 4x the image tokens of medium |
| `ALLOW_ORGANIC_PUBLISH` | Must be `true` to post to a real account |
| `GEMINI_PRIMARY_MODEL` / `GEMINI_UTILITY_MODEL` | Model names used when the provider is Gemini (both default to the small `gemini-3.5-flash-lite`) |

The DM agent uses the **utility** model (a few hundred input tokens plus the knowledge block per reply).
Switching `LLM_PROVIDER` between `gemini` and `litellm` (OpenAI or anything LiteLLM supports) needs no code change.

## Tests

- `uv run pytest` runs everything offline (scripted model, fake Meta). Needs MongoDB; set `TEST_MONGODB_URI`
  (the compose file's replica set works).
- `RUN_LIVE_GEMINI=1 GEMINI_API_KEY=... uv run pytest tests/live -s` runs the DM agent, the ad draft and organic
  posting against real Gemini with Meta still faked. Free-tier keys are limited to about 20 requests a day per model,
  and Gemini image generation needs billing; the image test skips itself on a quota error.
# Tunnel and image storage notes

Use the named Docker volume `acm-dev-mongo-data` whenever running the development database. GridFS stores the media library in MongoDB, so replacing a container without reusing this volume removes those images. `scripts/backup-db.ps1` creates a database archive.

For public tunnel sessions, `scripts/start-real.ps1 -PublicUrl ...` uses a production Next.js build because development chunk requests can fail through tunnels.

**Instagram media fetch limitation over Dev Tunnels (`devtunnels.ms`):**
Microsoft Dev Tunnels automatically displays an anti-phishing warning page for unauthenticated visitors when the client sends `Accept: text/html` (which Meta's `facebookexternalhit` image crawler always includes). This causes Instagram to fail with `"The media could not be fetched from this URI"`. `scripts/start-real.ps1` automatically launches a dedicated Cloudflare tunnel (`cloudflared`) to serve `PUBLIC_BASE_URL` image requests directly, allowing Instagram's servers to fetch the raw JPEG binary without interruption.
