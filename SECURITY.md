# Security Policy

## Supported Versions

The following versions of **Antigravity Voice Assistant** are currently supported with security updates:

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

The Antigravity Voice Assistant team takes security and user privacy seriously. We appreciate responsible disclosure of vulnerabilities.

If you discover a security vulnerability, please do **NOT** open a public issue or discussion.

Instead, please send a report to our private security contact:
- **Email / Security Contact:** `<SECURITY_CONTACT>`

### What to Include in Your Report
To help us triage and resolve the issue quickly, please include:
1. A clear description of the vulnerability and its potential impact.
2. Steps to reproduce the issue (including any proofs of concept, sample inputs, or environment parameters).
3. The affected subsystem (`desktop/`, `relay/`, or `android/`).
4. Any proposed remediations or mitigations, if available.

### Our Commitment
- We will acknowledge receipt of your report within 48 hours.
- We will keep you updated on our progress toward investigating and resolving the issue.
- Once a fix is verified and deployed, we will coordinate public disclosure with appropriate credit to the reporter.

## Operational & Architecture Security Invariants
- **Advisory Firewall**: The command firewall inside `desktop/firewall/` is a guard against accidental dangerous shell commands, not an impregnable defense against adversarial prompt injection. Always keep your Antigravity IDE native tool-use permissions configured to require approval for sensitive file operations and shell commands.
- **Fail-Closed Relays**: The Cloud Relay requires `RELAY_AUTH_SECRET` to be configured with at least 32 characters, enforces HMAC bearer authentication, and derives tenants strictly from verified credentials.
- **No Remote Auto-Execution**: Remote pair programming instructions sent over the relay are staged into the Antigravity chat input and never auto-submitted without human review.
