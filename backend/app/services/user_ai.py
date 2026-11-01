from app.config import Settings
from app.security.crypto import decrypt_token

KEY_FIELD = {"gemini": "gemini_api_key", "openrouter": "openrouter_api_key"}  # default: openai_api_key
LLM_PROVIDER = {"gemini": "gemini", "openrouter": "openrouter"}  # default: litellm (OpenAI)


async def settings_for_user(db, user_id, settings: Settings) -> Settings:
    record = await db.user_ai_settings.find_one({"user_id": user_id})
    if not record:
        return settings
    provider = record.get("provider")
    key_field = KEY_FIELD.get(provider, "openai_api_key")
    key = (
        decrypt_token(settings.token_encryption_key, record["api_key_ciphertext"])
        if record.get("api_key_ciphertext")
        else getattr(settings, key_field)
    )
    if not key:
        return settings
    update = {key_field: key, "llm_provider": LLM_PROVIDER.get(provider, "litellm")}
    if provider == "openrouter" and record.get("model_family"):
        update["openrouter_model_family"] = record["model_family"]
    return settings.model_copy(update=update)
