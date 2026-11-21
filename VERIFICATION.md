# Verification — MongoDB edition

Verified on 21 November 2026 using a real local MongoDB 8.0 replica set and PyMongo 4.15.4. **42 tests passed** (40 existing application checks plus 2 MongoDB-specific checks); React production build passed. No live email was sent by these tests.

From `server`, in the Python environment:

```bash
CLASSROOM_TEST_MONGODB_URI='mongodb://127.0.0.1:27028/?replicaSet=classroomtest' python -m pytest -q
```

Use only a disposable replica set. Tests create unique `classroom_test_*` databases and drop them afterward. Without this explicit URI tests skip; skipped checks are not success evidence.

Coverage: registration/verification, CSRF, authorization, failed-login alerts, sensor replay/authentication, website hooks, email queue, classroom progress, persistence across app instances, uniqueness, rollback, transaction conflicts, BSON value handling and SHAP/LIME reconstruction/repeatability. SMTP is mocked or uses local outbox mode.

```bash
npm --prefix client ci
npm --prefix client run build
```

Atlas, Vercel, real SMTP delivery and live network accuracy require checks after your own configuration. Historical metrics remain in `server/models/cic-tree/RESULTS.md`; no model retraining was performed for this database conversion.
