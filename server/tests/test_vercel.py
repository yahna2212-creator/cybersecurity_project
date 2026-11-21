import importlib.util
from pathlib import Path

from classroom import create_app
from security_app.app import db, queue_email
from security_app.mongo_store import Row
from security_app.mail import deliver


def entrypoint():
    spec = importlib.util.spec_from_file_location('vercel_entry', Path(__file__).resolve().parents[2] / 'app.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_missing_vercel_secrets_fail_closed(monkeypatch):
    for key in ['MONGODB_URI', 'SESSION_SECRET', 'PUBLIC_URL']:
        monkeypatch.delenv(key, raising=False)
    application = entrypoint().app
    result = application.test_client().get('/api/session')
    assert result.status_code == 503
    assert set(result.json['missing_configuration']) == {'MONGODB_URI', 'SESSION_SECRET', 'PUBLIC_URL'}
    assert 'no-store' in result.headers['Cache-Control']


def test_vercel_factory_has_no_database_connection_at_import(monkeypatch):
    monkeypatch.setenv('MONGODB_URI', 'mongodb://unused.invalid/classroom')
    monkeypatch.setenv('SESSION_SECRET', 'test-only-session-secret-not-a-real-credential')
    monkeypatch.setenv('PUBLIC_URL', 'https://preview.example.test')
    monkeypatch.setenv('VERCEL', '1')
    application = entrypoint().app
    assert application.config['INIT_DATABASE'] is False
    assert application.config['SESSION_COOKIE_SECURE']
    assert application.config['MAIL_MODE'] == 'disabled'
    assert application.extensions['flow_model'] is not None


def test_row_supports_named_and_positional_access():
    row = Row(id=5, email='sample@example.test')
    assert row[0] == row['id'] == 5


def test_disabled_mail_preserves_pending_queue(tmp_path):
    application = create_app({'TESTING': True, 'INSTANCE': str(tmp_path), 'MAIL_MODE': 'disabled'})
    with application.app_context():
        queue_email('sample@example.test', 'test', 'test')
        db().commit()
    assert deliver(application) == 0
    with application.app_context():
        assert db().execute('SELECT state FROM notifications').fetchone()[0] == 'pending'
    assert not (tmp_path / 'outbox').exists()


def test_mail_job_requires_secret_and_smtp(tmp_path, monkeypatch):
    application = create_app({'TESTING': True, 'INSTANCE': str(tmp_path), 'MAIL_MODE': 'disabled'})
    client = application.test_client()
    monkeypatch.delenv('CRON_SECRET', raising=False)
    assert client.get('/api/jobs/mail').status_code == 401
    monkeypatch.setenv('CRON_SECRET', 'test-only-cron-secret-at-least-32-characters')
    assert client.get('/api/jobs/mail', headers={'Authorization': 'Bearer wrong'}).status_code == 401
    result = client.get('/api/jobs/mail', headers={'Authorization': 'Bearer test-only-cron-secret-at-least-32-characters'})
    assert result.status_code == 503


def test_inline_delivery_is_opt_in(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr('security_app.mail.deliver', lambda application, limit: calls.append(limit))
    application = create_app({'TESTING': True, 'INSTANCE': str(tmp_path), 'MAIL_MODE': 'smtp', 'MAIL_DELIVERY': 'inline'})
    client = application.test_client()
    csrf = client.get('/api/session').json['csrf']
    response = client.post('/register', data={'csrf': csrf, 'email': 'test@example.test', 'password': 'test-password-long-enough'})
    assert response.status_code == 302
    assert calls == [2]
