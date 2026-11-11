import pytest
from fastapi.testclient import TestClient

def test_root_redirect(client: TestClient):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/app"

def test_app_index(client: TestClient):
    response = client.get("/app/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<title>CamGirl Multi-Stream</title>" in response.text
    
def test_app_css(client: TestClient):
    response = client.get("/app/app.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]
    assert "body.theme-dark" in response.text

def test_app_js(client: TestClient):
    response = client.get("/app/app.js")
    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    assert "const API_BASE = '/api/v1';" in response.text
