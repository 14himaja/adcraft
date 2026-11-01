from google.adk.apps import App
from google.adk.runners import InMemoryRunner
from google.genai import types


async def run_root(root, text: str = "go", state: dict | None = None):
    runner = InMemoryRunner(app=App(name="test_app", root_agent=root))
    session = await runner.session_service.create_session(
        app_name="test_app", user_id="u1", state=state or {}
    )
    message = types.Content(role="user", parts=[types.Part(text=text)])
    events = [e async for e in runner.run_async(user_id="u1", session_id=session.id, new_message=message)]
    session = await runner.session_service.get_session(
        app_name="test_app", user_id="u1", session_id=session.id
    )
    return events, session
