# AdCraft: Master Documentation Index
## AI-Powered Ad Campaign Manager — Internship Evaluation Project

---

### Welcome to the AdCraft Documentation Library

This documentation suite provides a complete, easy-to-read guide for understanding, reviewing, running, evaluating, and extending the **AdCraft AI-Powered Ad Campaign Manager**.

All documents are written in **simple, accessible English** so that engineering leads, product managers, and evaluation panel members can easily read and understand every architectural decision.

---

### Documentation Navigation Table

| # | Document Title | File Link | What You Will Learn |
|---|---|---|---|
| **01** | **Project Overview** | [`01_PROJECT_OVERVIEW.md`](./01_PROJECT_OVERVIEW.md) | What AdCraft is, the problem it solves, the core harness rule ("Model proposes, harness decides"), and key capabilities. |
| **02** | **Research Docs** | [`02_RESEARCH_DOCS.md`](./02_RESEARCH_DOCS.md) | Platform comparison (Meta, LinkedIn, TikTok, X, Google Ads), why Meta Marketing API v26.0 was selected, rate limits, and token lifecycle. |
| **03** | **High-Level Design (HLD)** | [`03_HIGH_LEVEL_DESIGN_HLD.md`](./03_HIGH_LEVEL_DESIGN_HLD.md) | High-level system architecture, component breakdown, end-to-end 16-step user flow, and non-negotiable safety invariants. |
| **04** | **Low-Level Design (LLD)** | [`04_LOW_LEVEL_DESIGN_LLD.md`](./04_LOW_LEVEL_DESIGN_LLD.md) | Backend package layout, MongoDB 10 collections & 23 indexes, 17 state transitions, Google ADK 2.x harness, self-repair loop, and crypto. |
| **05** | **API Designs** | [`05_API_DESIGNS.md`](./05_API_DESIGNS.md) | Complete REST API catalog (Auth, Campaigns, Meta, Organic, Hashtags, Media, DM Agent, Webhooks), error envelopes, and Meta Graph calls. |
| **06** | **Features & Requirements Matrix** | [`06_FEATURES_AND_REQUIREMENTS_MATRIX.md`](./06_FEATURES_AND_REQUIREMENTS_MATRIX.md) | Exhaustive line-by-line verification against the internship prompt, status checklist (96.5% functional coverage), and extra bonus features. |
| **07** | **Implementation Plan Phases** | [`07_IMPLEMENTATION_PLAN_PHASES.md`](./07_IMPLEMENTATION_PLAN_PHASES.md) | Walkthrough of Development Stages 1 to 9, engineering milestones, challenges solved, and bonus milestones (DM Agent, Organic Posting). |
| **08** | **Execution Steps & User Guide** | [`08_EXECUTION_STEPS_AND_USER_GUIDE.md`](./08_EXECUTION_STEPS_AND_USER_GUIDE.md) | Step-by-step local setup (MongoDB replica set, backend, frontend), automated test commands, offline mock mode, and 10 demo walkthroughs. |
| **09** | **Meta Account Details & Setup** | [`09_META_ACCOUNT_DETAILS_AND_SETUP.md`](./09_META_ACCOUNT_DETAILS_AND_SETUP.md) | Meta Developer Portal setup, Business App permissions, access tokens, Facebook Pages, Instagram Business accounts, webhooks, and spend safety. |
| **10** | **LLM Models & Switching Guide** | [`10_LLM_MODELS_AND_SWITCHING_GUIDE.md`](./10_LLM_MODELS_AND_SWITCHING_GUIDE.md) | Models used in AdCraft, how LiteLLM enables zero-code model switching, and copy-paste .env setups for Gemini, OpenAI, OpenRouter, and Offline. |

---

### Quick Start for Evaluators

1. **Want to understand the big picture in 2 minutes?**  
   Read [`01_PROJECT_OVERVIEW.md`](./01_PROJECT_OVERVIEW.md).

2. **Want to run the app locally right now?**  
   Follow the 4 steps in [`08_EXECUTION_STEPS_AND_USER_GUIDE.md`](./08_EXECUTION_STEPS_AND_USER_GUIDE.md).

3. **Want to verify which prompt requirements are done?**  
   Check the line-by-line table in [`06_FEATURES_AND_REQUIREMENTS_MATRIX.md`](./06_FEATURES_AND_REQUIREMENTS_MATRIX.md).

4. **Want to switch from Gemini to OpenAI or Offline Mock?**  
   See the ready-to-copy `.env` blocks in [`10_LLM_MODELS_AND_SWITCHING_GUIDE.md`](./10_LLM_MODELS_AND_SWITCHING_GUIDE.md).

5. **Want to inspect the technical audit report?**  
   Review [`ADCRAFT_COMPLETE_IMPLEMENTATION_AUDIT.md`](./ADCRAFT_COMPLETE_IMPLEMENTATION_AUDIT.md).
