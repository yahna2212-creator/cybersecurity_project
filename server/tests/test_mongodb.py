import sqlite3
import pytest
from classroom import create_app
from security_app.app import db, queue_email


def test_mongo_rollback_uniqueness_and_bson_values(tmp_path):
    app = create_app({'TESTING': True, 'INSTANCE': str(tmp_path)})
    with app.app_context():
        queue_email('rollback@example.test', 'Test', 'Test')
        db().rollback()
        assert db().execute('SELECT COUNT(*) FROM notifications').fetchone()[0] == 0
        strange = "a' OR 1=1 --@example.test"
        db().execute('INSERT INTO users(email,password) VALUES(?,?)', (strange, 'hash'))
        db().commit()
        assert db().execute('SELECT email FROM users WHERE email=?', (strange,)).fetchone()[0] == strange
        assert db().execute('SELECT email FROM users WHERE email=?', ({'$ne': None},)).fetchone() is None
        with pytest.raises(sqlite3.IntegrityError):
            db().execute('INSERT INTO users(email,password) VALUES(?,?)', (strange, 'hash'))
        db().rollback()
        assert db().execute('SELECT COUNT(*) FROM users').fetchone()[0] == 1
        assert db().database.users.count_documents({}) == 1
    assert not (tmp_path / 'security.sqlite3').exists()


def test_mongo_conflicting_transaction_preserves_committed_data(tmp_path):
    from pymongo.errors import OperationFailure
    from security_app.database import connect
    app = create_app({'TESTING': True, 'INSTANCE': str(tmp_path)})
    first, second = connect(app.config), connect(app.config)
    try:
        first.execute('INSERT INTO classroom_progress VALUES(1, ?)', ('{}',))
        with pytest.raises(OperationFailure):
            second.execute('INSERT INTO classroom_progress VALUES(2, ?)', ('{}',))
        second.rollback()
        first.commit()
        assert second.execute('SELECT COUNT(*) FROM classroom_progress').fetchone()[0] == 1
        second.execute('INSERT INTO classroom_progress VALUES(2, ?)', ('{}',))
        second.commit()
        assert first.execute('SELECT COUNT(*) FROM classroom_progress').fetchone()[0] == 2
    finally:
        first.close()
        second.close()
