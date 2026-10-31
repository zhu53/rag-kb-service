import httpx
import respx


async def test_http_is_mocked():
    with respx.mock:
        respx.post("https://api.example.com/v1/chat").respond(json={"reply": "假的"})
        async with httpx.AsyncClient(base_url="https://api.example.com") as client:
            resp = await client.post("/v1/chat", json={"q": "hi"})
        assert resp.json() == {"reply": "假的"}
