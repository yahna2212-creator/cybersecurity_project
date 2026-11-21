# MongoDB setup

## Atlas

Create a cluster and a dedicated database user with read/write access to the application database. Allow the application's outbound IPs in Network Access; prefer restricted access and keep TLS enabled. Set the Python driver's connection string as private `MONGODB_URI` (percent-encode special characters in credentials), and set `MONGODB_DB=classroom_security`. Use a separate database for preview.

Load these variables locally, enter `server`, run `python manage.py init-db`, then `python manage.py create-admin --email YOUR_ADMIN_EMAIL`. Initialization creates collections/indexes/counters without deleting existing records.

## Local replica set

With Docker installed, for local development only:

```bash
docker run -d --name classroom-mongo -p 127.0.0.1:27017:27017 mongo:8.0 --replSet rs0 --bind_ip_all
docker exec classroom-mongo mongosh --quiet --eval 'rs.initiate({_id:"rs0",members:[{_id:0,host:"localhost:27017"}]})'
```

Wait for primary election. Run Flask on the host with `MONGODB_URI=mongodb://127.0.0.1:27017/?replicaSet=rs0`. This passwordless local container is not a production setup. The supplied application Compose file expects an Atlas URI accessible from its containers; localhost inside a container is not the host database.

## Environment variables

| Variable | Purpose |
|---|---|
| `MONGODB_URI` | Private MongoDB URI; required |
| `MONGODB_DB` | Database name; default `classroom_security` |
| `SESSION_SECRET` | Random signing value; generate 64 hex characters |
| `PUBLIC_URL` | Public origin used for verification links; HTTPS when deployed |
| `ADMIN_EMAIL` | Central administrator alert recipient |
| `MAIL_MODE` | `outbox` locally, `disabled` to retain pending mail, or `smtp` |
| `MAIL_DELIVERY` | `inline` on Vercel; local worker uses `manual` |
| `SMTP_HOST`, `SMTP_PORT` | STARTTLS server, normally port 587 |
| `SMTP_FROM`, `SMTP_USER`, `SMTP_PASSWORD` | Authorized sender and private credentials |
| `SENSOR_TOKEN` | Separate private flow-ingestion token |
| `WEBSITE_ID`, `WEBSITE_TOKEN` | Optional external website integration |
| `COOKIE_SECURE` | `1` for HTTPS; `0` only locally |
| `TRUSTED_PROXY_HOPS` | `0` locally; `1` only behind a trusted proxy |
| `GEOIP_DB` | Optional separately licensed City MMDB file |

## Persistence and operations

`security_app/mongo_store.py` translates the application's fixed parameterized query dialect into native PyMongo operations. It is not a general SQL engine. Identifiers are allowlisted; values are BSON values. All persistent records live in MongoDB. sqlite3 is imported only for duplicate-key exception compatibility; no SQLite storage is used.

Transactions use snapshot reads and majority commits. A shared counter serializes writes for this low-volume prototype. Competing writes may return retryable HTTP 503 responses. This limits throughput; further design is needed for high-load operation. Unique indexes enforce account emails and event IDs.

Use one mail worker for the demonstration. SMTP acceptance is not inbox confirmation. A crash after SMTP sending but before recording success may produce a duplicate on retry. Check the outbox dashboard and actual inbox.

No PostgreSQL/Neon migration is included. Existing accounts, progress, alerts and queued mail are not copied. Use fresh accounts and validate before switching production. Use Atlas backups or MongoDB Database Tools, protect dumps and verify restoration. The obsolete SQLite backup command intentionally refuses to run.
