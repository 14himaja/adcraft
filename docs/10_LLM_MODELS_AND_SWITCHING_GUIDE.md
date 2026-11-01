# AdCraft: LLM Models & Model Switching Guide
## Supported AI Models, Architecture & Step-by-Step Provider Switching

---

### 1. Overview of AI Models Used in AdCraft

AdCraft utilizes generative models across four specialized subsystems:

```
+-----------------------------------------------------------------------------------+
|                            AI SUBSYSTEMS IN ADCRAFT                               |
+-----------------------------------------------------------------------------------+
| 1. AdDrafter Agent        | Generates ad headlines, primary body copy,            |
|                           | descriptions, CTA buttons, and runs the repair loop.  |
| 2. Post Understanding     | Extracts structured products, prices, discounts,      |
|                           | and offer validity from published posts (Multimodal). |
| 3. DM Customer Support    | Grounded Hybrid RAG agent answering customer DMs      |
|                           | on Instagram based on indexed post knowledge.         |
| 4. Hashtag Agent          | Recommends high-engagement, relevant hashtags.        |
| 5. Vector Embeddings      | Converts text into 3072-dimensional vector embeddings |
|                           | for semantic similarity search in MongoDB.            |
| 6. Image Generation       | Generates 1080x1080 JPEG ad creative graphics.        |
+-----------------------------------------------------------------------------------+
```

---

### 2. Supported Model Providers & Architecture

AdCraft is powered by the **Google Agent Development Kit (ADK) 2.x** with a unified **LiteLLM bridge** (`backend/app/agents/models.py`).

Because of this unified abstraction layer:
$$\mathbf{You\ NEVER\ need\ to\ change\ any\ code\ to\ switch\ models.}$$

You can switch between **Google Gemini**, **OpenAI**, **OpenRouter** (Claude, Llama, DeepSeek), **Local Ollama**, or **Offline Mock** mode simply by changing **two lines in your `.env` file**.

---

### 3. Step-by-Step Instructions: How to Switch Models

#### Setup A: Google Gemini (Recommended Default)
*Best for: Blazing-fast inference, high quality, generous free tier.*

1. Obtain a free Gemini API key from [Google AI Studio](https://aistudio.google.com/).
2. Open your `.env` file and set:
   ```env
   LLM_PROVIDER=gemini
   GEMINI_API_KEY=AIzaSyYourGeminiApiKeyHere

   # Primary Model for Drafting & DM Agent
   GEMINI_PRIMARY_MODEL=gemini-3.5-flash-lite

   # Utility Model for Hashtags & Quick Classifications
   GEMINI_UTILITY_MODEL=gemini-3.5-flash-lite

   # Embedding Model (3072 dimensions)
   GEMINI_EMBEDDING_MODEL=gemini-embedding-001

   # Image Generation Model
   IMAGE_PROVIDER=ai
   IMAGE_MODEL=gemini-2.5-flash-image
   ```
3. Restart the backend server. That's it!

---

#### Setup B: OpenAI (GPT-5 / GPT-4.5 / DALL-E)
*Best for: Industry benchmark performance and DALL-E image generation.*

1. Obtain an OpenAI API key from [platform.openai.com](https://platform.openai.com/).
2. Open your `.env` file and set:
   ```env
   LLM_PROVIDER=litellm
   OPENAI_API_KEY=sk-proj-YourOpenAIApiKeyHere

   # Primary Model
   LLM_PRIMARY_MODEL=gpt-5

   # Utility Model
   LLM_UTILITY_MODEL=gpt-5

   # Embedding Model
   EMBEDDING_MODEL=text-embedding-3-small

   # Image Generation via DALL-E
   IMAGE_PROVIDER=openai
   OPENAI_IMAGE_MODEL=gpt-image-1
   OPENAI_IMAGE_QUALITY=medium
   ```
3. Restart the backend server.

---

#### Setup C: OpenRouter (Access Claude 3.5 Sonnet, Llama 3, DeepSeek V3)
*Best for: Using one single API key to access models from Anthropic, Meta, DeepSeek, Mistral, Google, or OpenAI.*

1. Obtain an API key from [openrouter.ai](https://openrouter.ai/).
2. Open your `.env` file and set:
   ```env
   LLM_PROVIDER=openrouter
   OPENROUTER_API_KEY=sk-or-v1-YourOpenRouterKeyHere
   OPENROUTER_MODEL_FAMILY=gemini
   OPENROUTER_MAX_TOKENS=4096

   # If using Gemini family via OpenRouter:
   OPENROUTER_GEMINI_PRIMARY_MODEL=google/gemini-3.5-flash-lite
   OPENROUTER_GEMINI_UTILITY_MODEL=google/gemini-3.5-flash-lite

   # Or switch to OpenAI / Claude family via OpenRouter:
   # OPENROUTER_MODEL_FAMILY=openai
   # OPENROUTER_OPENAI_PRIMARY_MODEL=anthropic/claude-3.5-sonnet
   # OPENROUTER_OPENAI_UTILITY_MODEL=openai/gpt-4o-mini
   ```
3. Restart the backend server.

---

#### Setup D: 100% Offline / Scripted Mode (Zero Cost, No API Keys)
*Best for: Running automated evaluations, CI/CD pipelines, or testing offline with zero budget.*

1. In `.env`, set:
   ```env
   LLM_PROVIDER=scripted
   SCRIPTED_SCENARIO=ad_studio
   IMAGE_PROVIDER=fake
   META_MODE=fake
   MOCK_METRICS=true
   ```
2. In this mode:
   - The system uses pre-recorded deterministic JSON scenarios (`backend/app/agents/scenarios/ad_studio.json`).
   - Images are generated as deterministic colored squares with text.
   - Vector embeddings use mathematical SHA-256 n-gram coordinate hashing.
   - Zero network requests are made to external LLM providers.

---

#### Setup E: Local Models via Ollama (Llama 3 / Mistral)
*Best for: Running 100% private, self-hosted open-source models on your local GPU.*

1. Install and start [Ollama](https://ollama.ai/) with your preferred model:
   ```bash
   ollama run llama3
   ```
2. Open `.env` and configure LiteLLM to point to your local Ollama port:
   ```env
   LLM_PROVIDER=litellm
   LLM_PRIMARY_MODEL=ollama/llama3
   LLM_UTILITY_MODEL=ollama/llama3
   IMAGE_PROVIDER=fake
   ```
3. Restart the backend. LiteLLM routes all agent calls to `http://localhost:11434`.

---

### 4. Vector Embedding Model Deep Dive

AdCraft's **Dynamic Social Knowledge Engine** and **Hybrid RAG DM Agent** rely on vector embeddings to match customer inquiries to published ads.

- **Primary Embedding Model:** `gemini-embedding-001`
  - Produces **3072-dimensional normalized float vectors**.
  - Generated via Google Generative Language REST API (`models/gemini-embedding-001:embedContent`).
  - Stored in MongoDB `knowledge_chunks` collection.
- **Robustness Fallback:**
  - If the LiteLLM embedding call fails or encounters network timeout, `app/services/embeddings.py` automatically falls back to a direct `httpx` REST call to `generativelanguage.googleapis.com`.
  - In test / scripted mode, it uses `_deterministic_vector()` to produce normalized 64-dimensional vectors using SHA-256 word and bigram coordinate hashing.

---

### 5. Creative Image Generation Providers

AdCraft supports four distinct image generation strategies:

| Provider (`IMAGE_PROVIDER`) | Technology | Resolution & Format | Cost |
|---|---|---|---|
| `ai` | Pollinations AI REST endpoint | 1080x1080 JPEG | Free |
| `gemini` | Google Imagen (`gemini-2.5-flash-image`) | 1080x1080 JPEG | Standard Google AI pricing |
| `openai` | OpenAI DALL-E (`gpt-image-1`) | 1024x1024 centre-cropped to 1080 | Standard OpenAI pricing |
| `fake` | Deterministic PIL image generator | 1080x1080 colored square with text | Free / Offline |

All generated images pass through `normalize_square()` (`app/media/images.py`):
1. Centre-cropped to exact 1:1 aspect ratio.
2. Resized with high-quality Lanczos resampling to 1080x1080 pixels.
3. Encoded as JPEG quality 90.
4. Stored in MongoDB GridFS with SHA-256 deduplication.

---

### 6. Provider Summary & Quick Comparison

| Feature | Google Gemini | OpenAI | OpenRouter | Scripted / Offline |
|---|---|---|---|---|
| **Setup Speed** | 1 minute | 1 minute | 1 minute | Immediate |
| **API Key Required** | Yes (Free key available) | Yes (Paid account) | Yes (Pay per token) | **No Key Needed** |
| **Speed / Latency** | Ultra-Fast (~800ms) | Fast (~1.5s) | Variable | Instant (~10ms) |
| **Cost** | Free / Lowest | Moderate | Pay-as-you-go | **\$0.00** |
| **Ad Adherence** | Excellent (100% with repair) | Excellent | Excellent | 100% Deterministic |
