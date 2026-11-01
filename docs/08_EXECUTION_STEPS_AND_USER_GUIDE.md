# AdCraft: Execution Steps, Setup & User Guide
## Step-by-Step Local Setup, Testing & Demonstration Walkthrough

---

### 1. Prerequisites

Before running AdCraft, ensure your development machine has:
1. **Python:** Version 3.12 or newer.
2. **Node.js:** Version 18.x or 20.x with npm.
3. **Docker Desktop:** Installed and running (used to run MongoDB with replica set `rs0`).
4. **Git:** Installed.

---

### 2. Step-by-Step Local Setup

#### Step 1: Start MongoDB with Replica Set Support

AdCraft's cryptographic approval engine uses MongoDB multi-document ACID transactions. MongoDB requires a replica set (`rs0`) for transactions.

Run Docker Compose from the project root:
```bash
docker compose up -d mongo
```
*Note: This starts MongoDB 7.0 on port 27017 and automatically initializes replica set `rs0`.*

---

#### Step 2: Configure Backend Environment Variables

In the project root, make sure a `.env` file exists (or copy `.env.example` to `.env`).

Here is a ready-to-use development configuration:

```env
# Application Environment
APP_ENV=development
MONGODB_URI=mongodb://127.0.0.1:27017/acm?replicaSet=rs0
MONGODB_DB=acm

# Security & Secrets (32+ characters)
JWT_SECRET=synxa-internship-adcraft-secure-jwt-secret-key-32chars
TOKEN_ENCRYPTION_KEY=synxa-token-encryption-key-32bytes-hex-len

# AI Model Provider: "gemini" | "litellm" | "openrouter" | "scripted"
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_PRIMARY_MODEL=gemini-3.5-flash-lite
GEMINI_UTILITY_MODEL=gemini-3.5-flash-lite
GEMINI_EMBEDDING_MODEL=gemini-embedding-001

# Image Generation Provider: "gemini" | "openai" | "ai" | "fake"
IMAGE_PROVIDER=ai
IMAGE_MODEL=gemini-2.5-flash-image

# Meta Gateway Mode: "real" | "fake"
META_MODE=fake
MOCK_METRICS=true

# Spend Safety Switches (Keeps ads in PAUSED state)
ALLOW_REAL_AD_SPEND=false
SAFE_MODE_NO_SPEND=true
MAX_DAILY_BUDGET_INR=1000
MAX_CAMPAIGN_DAYS=30
```

---

#### Step 3: Run the Backend Server

Open a terminal, activate the Python virtual environment, and start FastAPI:

**On Windows (PowerShell):**
```powershell
cd backend
.\.venv\Scripts\activate
uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --reload
```

**On macOS / Linux:**
```bash
cd backend
source .venv/bin/activate
uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --reload
```

The backend API will start at: **`http://127.0.0.1:8000`**  
Interactive API docs (Swagger): **`http://127.0.0.1:8000/docs`**

---

#### Step 4: Run the Frontend Application

Open a second terminal window, navigate to the `frontend` folder, and start the Next.js dev server:

**On Windows / macOS / Linux:**
```bash
cd frontend
npm run dev
```

The frontend web application will start at: **`http://localhost:3000`**

Open your web browser and navigate to: **`http://localhost:3000`**

---

### 3. How to Run Automated Tests

#### A. Running Frontend Vitest Tests (144 Tests)
From the `frontend` directory:
```bash
npm test -- --run
```
*Expected Result: 23 test files passed, 144 tests passed (100% pass rate).*

#### B. Running Backend Pytest Tests (635 Tests)
From the `backend` directory with the virtual environment activated:
```bash
# Run all unit tests
pytest tests/unit

# Run all API route tests
pytest tests/api

# Run AI agent tests
pytest tests/agents

# Run Meta Gateway contract tests
pytest tests/contract

# Run SaaS multi-user isolation tests
pytest tests/integration/test_saas_multiuser.py
```

---

### 4. Zero-Cost Offline Mock Mode (No API Keys Needed)

If an evaluator wants to test the entire application without configuring a Google Gemini API key or a Meta developer account, AdCraft supports **100% offline mock mode**:

1. In `.env`, set:
   ```env
   LLM_PROVIDER=scripted
   META_MODE=fake
   IMAGE_PROVIDER=fake
   MOCK_METRICS=true
   ```
2. Restart the backend server.
3. The system will use deterministic JSON scenarios (`backend/app/agents/scenarios/`) for AI generation, create realistic mock images, and simulate Meta API responses seamlessly with zero API costs.

---

### 5. Ten Demonstration Scenarios Walkthrough

Here is a step-by-step guide to demonstrating the complete application:

#### Scenario 1: Conversational Brief Intake
1. Log into the application at `http://localhost:3000` (or register a new user).
2. On the dashboard, type in the chat box:
   > *"Run an Instagram ad for our new AI code-review SaaS tool targeting developers in India, ₹5,000 budget for 7 days."*
3. Click Send.
4. **Observe:** The AI extracts the budget, flight dates, audience, and geography. It notes that the landing page URL is missing and asks: *"Where should the ad send people?"*

#### Scenario 2: Clarification & Draft Generation
1. Reply in the chat:
   > *"Send them to https://example-ai.dev and create a compelling ad."*
2. **Observe:** The AI generates 3 copy variants, suggests targeting interests (`Python`, `Software Engineering`), calls the image generator, and opens the **AdCraft Studio**.

#### Scenario 3: AdCraft Studio & Live Mobile Preview
1. In the Studio modal, inspect the **6-section persistent sidebar**:
   - Section 1: Objective & Idea
   - Section 2: Target Audience
   - Section 3: Budget & Schedule
   - Section 4: Creative & Preview
   - Section 5: Hashtags
   - Section 6: Publishing
2. Click on **Section 4 (Creative & Preview)**.
3. **Observe:** The real-time interactive mobile phone mockup renders the ad exactly as it will appear on Instagram Feed and Stories.
4. Note the character counters: Headline (max 40), Primary Text (max 125), Description (max 30).

#### Scenario 4: AI Copy Revision & Visual Diff
1. In the chat or studio revision box, type:
   > *"Make the headline focus on cutting review time by 50%."*
2. Click **AI Polish**.
3. **Observe:** The AI rewrites the headline to stay under 40 characters. A new immutable version snapshot is created, and the visual diff shows exactly what changed.

#### Scenario 5: Cryptographic Approval Gate
1. Navigate to **Section 6 (Publishing)**.
2. Click **Review & Publish**.
3. **Observe:** A pre-publish summary verifies all required fields are complete.
4. Click **Approve**. A modal displays the ad account, Page, budget, dates, and spend warning.
5. Confirm approval. The system generates an atomic approval record tied to the SHA-256 content hash.

#### Scenario 6: Re-Approval Invalidation (Safety Demonstration)
1. After approving, go back to **Section 4** and edit one word in the headline.
2. Return to **Section 6**.
3. **Observe:** The approval is immediately invalidated! Status resets to `IN_REVIEW`. The system blocks publishing until the user explicitly re-approves the modified version.

#### Scenario 7: Resilient Checkpointed Publishing
1. Re-approve the campaign and click **Publish**.
2. **Observe:** A step-by-step progress indicator tracks:
   - Step 1: Uploading Creative Image
   - Step 2: Creating Meta Campaign (PAUSED)
   - Step 3: Creating Ad Set
   - Step 4: Creating Ad Creative
   - Step 5: Creating Ad Object
3. The campaign status updates to `PAUSED` (or `ACTIVE` if spend allowed), and external Meta IDs are saved.

#### Scenario 8: Organic Social Publishing (Zero Spend)
1. Click **Organic Posts** in the main navigation.
2. Type a post caption: *"Super excited to launch AdCraft! #AI #Marketing"*.
3. Select an image from the Media Library or generate one with AI.
4. Choose destinations: **Instagram Feed** and **Facebook Feed**.
5. Click **Publish Organic Post**.
6. **Observe:** The post is published via Meta's Content Publishing API with zero advertising spend.

#### Scenario 9: 24/7 Instagram DM Customer Support Agent
1. Click **DM Agent** in the main navigation.
2. Click the **"Try It" Preview Simulator**.
3. Type: *"Is the 20% discount on the developer tool still active?"*
4. Click Send.
5. **Observe:** The AI DM agent resolves the post reference via **Hybrid RAG**, checks offer validity from the ingested post, and responds with accurate pricing and discount details in friendly conversational English.

#### Scenario 10: Performance Analytics & AI Optimization Proposals
1. Navigate to the **Insights** tab for any published campaign.
2. Select the date filter (e.g. "Last 7 Days").
3. **Observe:** KPI cards render Impressions, Reach, Clicks, Spend, and CTR.
4. Read the **AI Diagnostic Report**:
   - Statements are separated into **Fact, Calculation, Assumption, and Recommendation**.
   - Notice the actionable proposal card: *"Pause Variant B (CTR 0.32%), reallocate budget to Variant A (CTR 1.15%)"*.
   - Clicking "Apply Change" prompts for human confirmation and updates the live campaign.
