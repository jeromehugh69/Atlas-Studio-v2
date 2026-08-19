from fastapi.testclient import TestClient

from atlas_studio.main import app


with TestClient(app) as client:
    tools = client.get("/api/tool-library")
    sources = client.get("/api/sources")
    page = client.get("/static/index.html")
    assert tools.status_code == 200 and len(tools.json()) == 20
    assert sources.status_code == 200 and len(sources.json()) == 3
    assert client.get("/api/sources/atlas-readme/content").status_code == 200
    sections = ["tasksView", "plans", "implementation", "codeView", "toolsView", "knowledge", "sources", "qa", "sandbox", "environments"]
    assert all(f'id="{section}"' in page.text for section in sections)
    request = client.post(
        "/api/tool-library/deployment/request",
        json={"environment": "production", "reason": "Review production deployment access"},
    )
    assert request.status_code == 200
    assert request.json()["capability_granted"] is False
    print("routes_ok feature_pages=10 tool_grant=false")
