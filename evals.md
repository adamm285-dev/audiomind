# Empirical Standing & Ground Truth (Evals)
<!-- SPEC-001 v1.9.0 Pillar 7 | Mutability: CRYPTOGRAPHIC -->
<!-- Corpus Diversity Invariant: Unique SHA-256 digests required across all golden fixtures -->

## 1. Golden Reference Corpus & Diversity
| Asset ID | Path / Scenario | SHA-256 (8-char) | Unique Characteristics | Target Subsystem |
| :--- | :--- | :--- | :--- | :--- |
| `TC-INIT` | `tests/fixtures/init.txt` | 8ca3b82b88a0f82559ebc4f0804792fe0cbb98e701d2f6f4fb334a1f0b3405c4 | Baseline golden reference | Core Engine |

## 2. Baseline Empirical Scorecard
- Baseline Commit: 46ddc93 (Pre-Release Hardened Release)
- Test Suite Status: ALL PASSING
  - Cloud Relay: 7/7 passed (`pytest relay/test_relay.py`)
  - Desktop HUD, Firewall, Remote Security, Focus Guard, Elevation Check, Playback Navigation & Highlight Reader: 37 passed (`pytest desktop/tests/`)
  - Desktop Model Inference: 10/12 passed (83.3% accuracy, `desktop/tests/test_model_inference.py`)
  - Android Companion: 28/28 tasks verified (`gradlew testDebugUnitTest`)
- Security & PII Audits: 0 sensitive matches across git tree. All fail-closed gates active.
