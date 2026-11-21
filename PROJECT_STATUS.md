# Scope and limitations

| Component | Included | Boundary |
|---|---|---|
| Classroom | Verified login, progress and admin pages | Fresh MongoDB accounts; no migration |
| Account detection | Failed-login and multi-account source rules | Mistakes/shared IPs can trigger false positives |
| Flow detection | CIC-trained tree, four raw measurements and derived features | Binary benign/attack, not all attack types |
| Explanations | SHAP, LIME, tree/rule evidence | Model behavior, not causality or intent |
| Response | Advisory steps and email | No automatic blocking |
| User notification | Applicable alerts to verified affected accounts | Flow-only traffic does not identify a registered user |
| Location | Optional GeoIP | Approximate network location, not exact tracking |
| Sensor | CSV replay and experimental Zeek adapter | Vercel does not capture network packets |
| MongoDB | Transactional collections | Replica set required; limited write throughput |
| Email | Local preview or SMTP | Acceptance is not inbox proof; rare duplicates possible |

The research contribution is evaluated integration of established detection, explanation, expert-rule and response techniques, not invention of each component.

Historical tree F1 is approximately 0.981 on the same-distribution test and 0.464 on Friday development data, demonstrating a generalization gap. Friday had already been examined; it is not pristine external validation. TrafficLabelling and MachineLearningCSV are representations of the same benchmark, not independent datasets.

MongoDB checks verify application behavior, not attack-detection accuracy. SHAP reconstruction and LIME repeatability do not establish explanation stability for every input. Inspect LIME local fidelity. Raw CIC files are excluded; obtain them separately for retraining.

Demonstrate with a disposable verified local account: make ten incorrect login attempts, review the account alert and notifications, and check ordinary users cannot access admin pages. Use a small authorized CSV replay separately for flow explanations. Do not attack third-party systems.
