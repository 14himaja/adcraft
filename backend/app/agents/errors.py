from app.errors import AppError


class ModelUnavailable(AppError):
    status, code = 503, "LLM_UNAVAILABLE"


class TurnFailed(AppError):
    status, code = 422, "AI_OUTPUT_INVALID"
