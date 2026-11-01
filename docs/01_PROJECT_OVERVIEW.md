# AdCraft: AI-Powered Ad Campaign Manager
## Project Overview & Executive Summary

---

### What is AdCraft?

**AdCraft** is an intelligent web application that lets anyone create, launch, and monitor social media advertising campaigns simply by **talking to an AI assistant**.

Instead of struggling with complicated menus, confusing advertising settings, and strict platform rules on Meta Ads Manager (Facebook and Instagram), a user can simply say:

> *"I want to run an Instagram ad for our new AI code-review tool targeting software developers in India with a budget of ₹5,000 for 7 days."*

AdCraft takes this simple sentence and automatically:
1. Understands the product, target audience, budget, and dates.
2. Identifies any missing details and asks friendly follow-up questions.
3. Researches real audience interests and locations on Meta.
4. Generates professional ad headlines, body text, call-to-action buttons, and creative images.
5. Displays a realistic mobile preview of how the ad will look on Instagram Feed and Stories.
6. Allows the user to edit anything or ask the AI to rewrite copy.
7. Publishes the campaign safely to Meta once the user gives explicit approval.
8. Monitors impressions, clicks, spend, and click-through rates (CTR).
9. Explains campaign performance in plain English and suggests improvements.
10. Automatically answers customer questions in Instagram Direct Messages (DMs) using an AI assistant trained on the published posts.

---

### The Problem It Solves

Running paid advertisements on social media is essential for modern businesses, but existing tools present huge challenges:

1. **Complexity:** Meta Ads Manager has hundreds of confusing settings, checkboxes, and terms (CPM, CPC, custom conversions, placements).
2. **Strict Rules:** Meta strictly limits headline length (40 characters), description length (30 characters), and bans specific claims or guarantees. Exceeding these limits leads to ad rejection.
3. **Budget Risk:** Mistakes in campaign settings can accidentally spend thousands of dollars in minutes without warning.
4. **Disconnected Customer Care:** When ads succeed and customers send Instagram DMs asking about pricing or offers, human teams cannot respond 24/7, leading to lost sales.

**AdCraft solves all four problems:**
- It replaces complex dashboards with a natural, conversational interface.
- It automatically enforces all character limits and policy rules before anything is published.
- It includes safety switches and cryptographic approval gates so real money is never spent accidentally.
- It connects ads directly to an intelligent Instagram DM customer support agent.

---

### The Core Architectural Rule: "The Model Proposes, the Harness Decides"

In many naive AI applications, the AI model is given full freedom to call APIs, spend money, or publish content. This often leads to severe bugs, hallucinations, policy violations, and accidental spending.

AdCraft follows a strict engineering principle:

$$\mathbf{The\ AI\ Model\ Proposes\ \longrightarrow\ The\ Deterministic\ Harness\ Decides}$$

```
+-------------------------------------------------------------+
|                     USER CONVERSATION                       |
|           "Target developers in India for ₹5,000"           |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|                     AI MODEL (LLM)                          |
|  - Understands language and context                         |
|  - Proposes ad headlines, body copy, and creative ideas     |
|  - Proposes target audience interests                       |
+-------------------------------------------------------------+
                              |
                              v (Untrusted Proposal)
+-------------------------------------------------------------+
|              APPLICATION HARNESS (PYTHON CODE)              |
|  - Checks character counts: Headline <= 40 chars            |
|  - Checks budget: Minimum ₹50/day, Maximum ₹1,000/day       |
|  - Checks duration: Maximum 30 days                         |
|  - Checks prohibited words: No fake guarantees or claims    |
|  - Validates against official Meta Graph API requirements   |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|                  HUMAN APPROVAL GATEWAY                     |
|  - Shows the user exactly what will be published            |
|  - Requires explicit user click ("Approve & Publish")       |
|  - Records a cryptographic SHA-256 hash of the approved ad  |
+-------------------------------------------------------------+
                              |
                              v (Approved)
+-------------------------------------------------------------+
|                    META GRAPH API v26.0                     |
|  - Creates Campaign, Ad Set, Ad Creative, and Ad on Meta    |
+-------------------------------------------------------------+
```

1. **The AI Model** does what language models are best at: creativity, writing persuasive copy, extracting requirements, and answering questions.
2. **The Software Harness** does what deterministic code is best at: counting characters, validating budgets, checking permissions, encrypting tokens, enforcing state transitions, and managing database records.
3. **The AI Model NEVER has permission to publish or spend money.** Only the human user clicking the approve button can trigger publishing.

---

### Complete End-to-End User Journey

Here is what using AdCraft looks like from start to finish:

```
[ Step 1: Chat Brief ]
User types idea in chat -> AI extracts product, budget, audience, dates.

[ Step 2: Clarification ]
If information is missing (e.g., website link), AI asks friendly questions.

[ Step 3: Plan & Creative Generation ]
System generates 3 copy variations and creates a custom 1:1 image.

[ Step 4: AdCraft Studio Review ]
User explores the 6-section studio: Objective, Audience, Budget, Creative Preview, Hashtags, and Publishing.

[ Step 5: User Feedback & AI Revision ]
User can edit text directly or type: "Make the headline punchier". AI updates the draft in real time.

[ Step 6: Explicit Human Approval ]
User reviews the exact ad account, Page, budget, and creative, then clicks "Approve & Publish".

[ Step 7: Publishing to Meta ]
System uploads the image, creates the Meta campaign, ad set, creative, and ad objects via official API.

[ Step 8: Dynamic Social Knowledge Ingestion ]
The published ad is automatically indexed into a vector database so the DM agent knows about it.

[ Step 9: Analytics & Performance Insights ]
System collects impressions, clicks, spend, and CTR. AI analyzes trends and flags recommendations.

[ Step 10: 24/7 Instagram DM Assistant ]
When customers click the ad and send a DM ("What is the price?"), the AI DM agent answers accurately.
```

---

### Key Highlights & Features

| Feature | Description |
|---|---|
| **Conversational Brief** | Start with plain English; AI identifies missing fields and guides you. |
| **AdCraft Studio** | Modern 6-section sidebar interface with real-time mobile preview mockups. |
| **Multi-Placement Publishing** | Publish to Instagram Feed, Instagram Stories, Facebook Feed, and Facebook Stories. |
| **Organic Post Publishing** | Publish free organic posts to Instagram and Facebook with zero ad spend required. |
| **AI Hashtag Generator** | Recommends relevant hashtags by analyzing your ad text, plus an explore library. |
| **Checkpointed Publishing** | Resilient 7-step publisher. If internet drops on step 4, you can resume without duplicating ads. |
| **Spend Safety Switch** | Ads are created in `PAUSED` status. Real money is never spent unless explicit spend switches are turned on. |
| **Instagram DM Agent** | Automatically answers customer inquiries on Instagram using Hybrid RAG grounded in your published posts. |
| **AI Performance Reports** | Explains campaign metrics, separates facts from assumptions, and suggests actionable fixes. |
| **Multi-Model Support** | Easily switch between Google Gemini, OpenAI, OpenRouter, and offline mock models in seconds. |
| **Multi-Tenant SaaS** | Complete user signup, login, encrypted sessions, and workspace data isolation. |

---

### Technology Stack Summary

- **Frontend:** Next.js 16 (React 19, TypeScript 5, Tailwind CSS v4, Lucide Icons).
- **Backend:** FastAPI (Python 3.12), Pydantic v2, Structlog, Uvicorn.
- **Database & Storage:** MongoDB 7.0 (Motor async driver), GridFS image store.
- **AI Agent Framework:** Google Agent Development Kit (ADK 2.x) with LiteLLM bridge.
- **LLM Providers:** Google Gemini (`gemini-3.5-flash-lite`, `gemini-2.5-flash`), OpenAI (`gpt-5`, `gpt-4.5`), OpenRouter, and Scripted offline models.
- **Vector Embeddings:** Google `gemini-embedding-001` (3072-dimensional normalized vectors).
- **Image Generation:** Google Imagen, OpenAI DALL-E, Pollinations AI, and offline deterministic fallback.
- **Social Media API:** Meta Marketing API v26.0 (`facebook-business` SDK) & Meta Graph API.
- **Security:** Argon2id password hashing, AES-256-GCM token encryption, HMAC-SHA256 webhook signatures.
- **Test Coverage:** 144 Frontend Vitest tests (100% pass) and 635 Backend Pytest tests.

---

### Summary

AdCraft bridges the gap between powerful generative AI and the strict, high-stakes world of digital advertising. By pairing an intuitive conversational interface with a bulletproof, deterministic engineering harness, it makes launching and managing high-performing social media campaigns effortless, safe, and reliable.
