import os
from fastapi.testclient import TestClient
from app.main import app
from app.simulation import DrivingWorld, run_episode
from app.personality import comment

client = TestClient(app)

def test_health():
    assert client.get('/health').json()['mode'] == 'simulation'

def test_auth_missing():
    assert client.post('/episodes', json={'seed': 1}).status_code == 401

def test_auth_success():
    os.environ['APEX_API_KEY'] = 'test-only-secret'
    try:
        response = client.post('/episodes', json={'seed': 1}, headers={'X-Apex-Key': 'test-only-secret'})
        assert response.status_code == 200
        assert response.json()['steps'] <= 150
    finally:
        del os.environ['APEX_API_KEY']

def test_repeatable():
    assert run_episode(4) == run_episode(4)

def test_bounded():
    world = DrivingWorld()
    world.step(500, 500)
    assert 0 <= world.state.speed <= 2

def test_disclosure():
    assert 'AI gaming' in comment('start')['disclosure']