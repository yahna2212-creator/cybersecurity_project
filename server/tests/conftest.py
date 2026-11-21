"""Each test gets its own database on an explicitly supplied disposable replica set."""
import os
import uuid
import pytest
from pymongo import MongoClient

@pytest.fixture(autouse=True)
def isolated_mongodb(monkeypatch):
    uri = os.environ.get('CLASSROOM_TEST_MONGODB_URI')
    if not uri:
        pytest.skip('Set CLASSROOM_TEST_MONGODB_URI to a disposable MongoDB replica set')
    name = 'classroom_test_' + uuid.uuid4().hex
    monkeypatch.setenv('MONGODB_URI', uri)
    monkeypatch.setenv('MONGODB_DB', name)
    yield
    with MongoClient(uri) as client:
        client.drop_database(name)
