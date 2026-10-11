# MOCKS.md: Mock Inventory (Gate L)
<!-- SPEC-001 v1.9.0 Mock Ledger | Mutability: IN-STRIDE (same commit as the mock) -->

Every place where product code stands in for real behavior: simulated API responses, seeded or
hardcoded data, demo-only keys or endpoints, offline stubs, and fallbacks that fake success.
Test doubles are out of scope (Gate Q audits tests).

**Markers.** Mark each mock where it lives with a comment carrying its ID: `# MOCK(M-NNN): <what it fakes>`
(`// MOCK(M-NNN): ...` in JS/TS, Go, Rust, Java and similar). `sdcs verify --mocks` fails if a marker has no
entry, an entry has no marker, an entry and its markers list different files, or a listed `path::symbol`
does not exist.

**Format.** One `### M-NNN: title` heading per entry (real IDs use digits, e.g. M-001), then four fields:

- **Where:** one or more backticked `path::symbol` (Python: `function`, `Class`, `Class.method` or a
  module-level name; other languages: a declared function, class, const or method name)
- **What it fakes:** the real behavior this replaces
- **Why:** why the mock exists
- **To make it real:** what replacing it requires

Never reuse an ID. When a mock is removed, delete its markers and its entry together and list the ID
under "Retired IDs".

**Retired IDs:** none
