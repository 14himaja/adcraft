async def test_generated_correlation_id_is_returned(client):
    response = await client.get("/health")
    assert len(response.headers["x-correlation-id"]) == 32


async def test_safe_incoming_correlation_id_is_echoed(client):
    response = await client.get("/health", headers={"X-Correlation-ID": "req-42"})
    assert response.headers["x-correlation-id"] == "req-42"


async def test_unsafe_incoming_correlation_id_is_replaced(client):
    response = await client.get("/health", headers={"X-Correlation-ID": "bad id\nINJECTED"})
    assert response.headers["x-correlation-id"] != "bad id\nINJECTED"
    assert len(response.headers["x-correlation-id"]) == 32
