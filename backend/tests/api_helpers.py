PASSWORD = "long-enough-pw"


async def login(client, email: str = "dev@example.com") -> None:
    await client.post("/auth/register", json={"email": email, "password": PASSWORD})
    response = await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text


async def connect_fake_meta(client) -> None:
    assert (await client.get("/meta/connect")).status_code == 302
    response = await client.put(
        "/meta/connection", json={"ad_account_id": "act_fake_1", "page_id": "page_fake_1"}
    )
    assert response.status_code == 200, response.text
