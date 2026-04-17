from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

response = client.get("/api/health")
print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")