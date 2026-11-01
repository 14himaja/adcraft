async def register(client, email="dev@example.com", password="long-enough-pw"):
    return await client.post("/auth/register", json={"email": email, "password": password})


async def login(client, email="dev@example.com", password="long-enough-pw"):
    return await client.post("/auth/login", json={"email": email, "password": password})


async def test_register_creates_user_with_hashed_password(client, db):
    response = await register(client)
    assert response.status_code == 201
    user = await db.users.find_one({"email": "dev@example.com"})
    assert user["password_hash"] != "long-enough-pw"


async def test_register_lowercases_email(client, db):
    await register(client, email="Dev@Example.com")
    assert await db.users.find_one({"email": "dev@example.com"})


async def test_duplicate_email_is_409_with_envelope(client):
    await register(client)
    response = await register(client)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_TAKEN"


async def test_short_password_is_422_with_envelope(client):
    response = await register(client, password="short")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


async def test_login_sets_httponly_lax_session_cookie(client):
    await register(client)
    response = await login(client)
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert cookie.startswith("session=")
    assert "httponly" in cookie
    assert "samesite=lax" in cookie


async def test_wrong_password_and_unknown_email_look_the_same(client):
    await register(client)
    wrong = await login(client, password="wrong-password")
    unknown = await login(client, email="nobody@example.com")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]


async def test_me_requires_a_session(client):
    response = await client.get("/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_me_returns_user_after_login(client):
    await register(client)
    await login(client)
    response = await client.get("/auth/me")
    assert response.status_code == 200
    assert response.json()["email"] == "dev@example.com"


async def test_logout_clears_session(client):
    await register(client)
    await login(client)
    await client.post("/auth/logout")
    assert (await client.get("/auth/me")).status_code == 401


async def test_login_is_rate_limited(client):
    await register(client)
    for _ in range(10):
        await login(client, password="wrong-password")
    response = await login(client, password="wrong-password")
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"


async def test_register_and_login_are_audited(client, db):
    await register(client)
    await login(client)
    events = [e["event_type"] async for e in db.audit_log.find({}, {"event_type": 1})]
    assert events == ["USER_REGISTERED", "USER_LOGIN"]
