# Macro Acceptance Contract (The North Star)
<!-- SPEC-001 v1.9.0 Pillar 3 | Mutability: BIMODAL ([INTENT] vs [MEASURED]) -->
<!-- Iron Invariant: NO TASK QUEUES. Ephemeral tasks belong exclusively in state.md -->

## Milestone M-001: Pre-Release Security Audit & Open-Source Sanitization
* [INTENT]: Purge all hardcoded credentials, personal file paths, device IPs, and tokens. Ensure all 3 subsystems (Desktop, Relay, Android) pass comprehensive unit and integration test suites under zero-trust boundaries.
* [MEASURED]: 100% tests passing across relay (3/3), desktop (7/7 + wake-word inference), and Android (27 tasks up to date). Clean Git tree verified with 0 sensitive matches. Status: VERIFIED.

## Milestone M-002: Public Open-Source Release & SDCS Bootstrapping
* [INTENT]: Provide full open-source readiness: Apache 2.0 license, .env.example, polished README quickstart, and SDCS 7-pillar cognitive scaffolding.
* [MEASURED]: License, env templates, and SDCS v1.9.0 scaffolding active; git hooks configured. Status: VERIFIED.

## Milestone M-003: Pre-Release Adversarial Hardening
* [INTENT]: Remediate all 8 adversarial audit items: fail-closed relay auth, derived tenant tokens, desktop gated remote listener without auto-submit, Android secure preferences, HTTPS enforcement, staged intent confirmations, firewall prefix bug resolution, dependency pinning, and security policy.
* [MEASURED]: 100% tests passing across relay (7/7), desktop firewall, HUD, speech player navigation, intent matcher & tri-state elevation security (34/34 passed), and Android companion unit tests (28/28 tasks). Git tree 100% sanitized with 0 matches for PII or leaked tokens. Status: VERIFIED.
