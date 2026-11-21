"""MongoDB-only database boundary; no implicit local persistence fallback."""
from security_app.mongo_store import MongoStore


def connect(config):
    uri = config.get('MONGODB_URI')
    name = config.get('MONGODB_DB', 'classroom_security')
    if not uri or not uri.startswith(('mongodb://', 'mongodb+srv://')):
        raise ValueError('Configure MONGODB_URI before starting the application')
    if not name or any(c in name for c in '/\\. "$*<>:|?'):
        raise ValueError('Invalid MONGODB_DB name')
    return MongoStore(uri, name)


def initialize(connection, script=None, postgres=False):
    connection.initialize()
