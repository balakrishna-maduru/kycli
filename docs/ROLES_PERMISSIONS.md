# 🔐 User Roles & Permissions (RBAC)

> **Status: Design only — not yet implemented.** Target release: **v0.5.0**.
> Nothing in this document changes current behavior. `kyacl readonly` and
> `kyacl key` keep working exactly as they do today, and every workspace is
> unaffected until it is explicitly opted in via `kyacl enable`.

## 1. Problem

Today, access control in `kycli` is a single shared secret per workspace:

- `kyacl readonly on|off` — blocks **all** writes, for **everyone**.
- `kyacl key set <value>` — one shared password (`KYCLI_ACCESS_KEY`) gates writes.

There is no concept of identity (who did this?), no distinction between
*read* and *write* and *administer*, and no way to scope access to a subset
of keys. This is fine for a single developer on a laptop, but breaks down as
soon as a workspace file is shared — a CI service account, a teammate, a
reporting job hitting the same `.db` over a network mount — because every
holder of the one secret has the same all-or-nothing power.

## 2. Goals / Non-Goals

**Goals**
- Named **principals** (not OS users) authenticated by a per-principal token.
- A small fixed set of **roles** (`owner`, `admin`, `writer`, `reader`) bound
  to principals **per workspace**.
- Optional **key-level overrides** (allow/deny specific verbs on keys
  matching a pattern), taking precedence over the workspace-level role.
- Fully **opt-in and backward compatible** — existing workspaces and scripts
  keep working unchanged until `kyacl enable` is run.
- Every grant, revoke, and denial is **audited**.

**Non-goals (v1)**
- Not a network auth server — still a local, file-based engine.
- Not OS-account integration — principals are `kycli`-level identities, not
  `$USER`.
- Not a defense against an attacker with raw filesystem access to the `.db`
  file (that's what the existing AES-256-GCM master-key encryption is for —
  RBAC is *authorization*, encryption is *confidentiality*; see §8).

## 3. Concepts

| Term | Meaning |
| :--- | :--- |
| **Principal** | A named identity (`alice`, `ci-bot`) created inside a workspace, authenticated by a token. |
| **Role** | A fixed bundle of permission verbs: `owner`, `admin`, `writer`, `reader`. |
| **Workspace-level binding** | `principal → role` for the whole workspace (the default). |
| **Key-level override** | `principal, key pattern → allow/deny verbs`, takes precedence over the workspace role for matching keys. |
| **Anonymous principal** | The implicit identity when no token is supplied. Exists so RBAC can be introduced gradually. |

### Roles → permission verbs

| Verb | owner | admin | writer | reader |
| :--- | :---: | :---: | :---: | :---: |
| `read` (`kyg`, `kyl`, `kyv`, search, `peek`) | ✅ | ✅ | ✅ | ✅ |
| `write` (`kys`, `kypatch`, `kypush`, append/collection ops) | ✅ | ✅ | ✅ | ❌ |
| `delete` (`kyd`, `kyclear`, consuming `kypop`) | ✅ | ✅ | ✅ | ❌ |
| `manage_acl` (`kyacl user/role/...`) | ✅ | ✅ | ❌ | ❌ |
| `manage_workspace` (`kyttl set`, type set, rename, `kyco`) | ✅ | ✅ | ❌ | ❌ |
| `admin` (master-key rotation, `kydrop`, backup/restore) | ✅ | ❌ | ❌ | ❌ |

Custom roles (arbitrary verb subsets) are deferred to Phase F — see §10.

## 4. Data Model

New tables, created lazily inside each workspace's existing `.db` file
(same file `workspace_meta` already lives in), guarded by the same
`_exclusive()` flock + atomic-rename pattern used for every other mutation
(see `kycli/core/storage.pyx`):

```sql
CREATE TABLE IF NOT EXISTS principals (
  id INTEGER PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,
  token_hash TEXT NOT NULL,      -- PBKDF2-HMAC-SHA256, same KDF as SecurityManager
  disabled INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workspace_roles (
  principal_id INTEGER NOT NULL REFERENCES principals(id),
  role TEXT NOT NULL,            -- owner|admin|writer|reader
  granted_by INTEGER,
  granted_at TEXT NOT NULL,
  PRIMARY KEY (principal_id)
);

CREATE TABLE IF NOT EXISTS key_acl (
  id INTEGER PRIMARY KEY,
  principal_id INTEGER NOT NULL REFERENCES principals(id),
  key_pattern TEXT NOT NULL,     -- Python regex, same convention as `kyl`/search (re.search, case-insensitive)
  allow_verbs TEXT,              -- comma list, e.g. "read,write"
  deny_verbs TEXT,
  priority INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
```

`workspace_meta` gains one new flag: `rbac_enabled` (`"0"`/`"1"`), read the
same way as the existing `readonly` and `access_key` settings.

Principals and bindings are **per-workspace** (not global), matching the
existing file-per-workspace isolation model — no cross-workspace identity
store to keep in sync, at the cost of re-creating principals per workspace.

## 5. Policy Evaluation

Precedence, evaluated on every call that resolves a key (read or write):

1. **`readonly` kill switch** — if set, deny all writes regardless of RBAC
   (unchanged from today — global override, even `owner` can't write).
2. If `rbac_enabled = 0` → **legacy path**: today's `access_key`/`readonly`
   check only. Nothing else in this document applies.
3. Resolve the calling principal from the supplied token (`anonymous` if
   none).
4. Collect `key_acl` rows for that principal whose `key_pattern` matches the
   target key, ordered by `priority` desc.
5. If any matching rule **denies** the requested verb → deny.
6. Else if any matching rule **allows** the requested verb → allow.
7. Else fall back to the principal's **workspace-level role** permission
   table (§3) → allow/deny.
8. Log the decision (denials always; grants/revokes always) via
   `AuditManager`.

Deny always beats allow at the same specificity, matching the precedent set
by AWS IAM / POSIX ACLs — this avoids surprising "but I thought I revoked
that" bugs.

## 6. CLI Surface

Extends the existing `kyacl` command (it already owns ACL concerns via
`kyacl readonly` / `kyacl key`):

```bash
# Toggle enforcement for the active workspace (off by default — see §9)
kyacl enable
kyacl disable
kyacl status                     # rbac: on/off, principal count, active role of caller

# Principals
kyacl user add <name>            # prints the token ONCE — store it now, it is not recoverable
kyacl user list
kyacl user disable <name>
kyacl user rotate-token <name>   # issues a new token, invalidates the old one immediately

# Workspace-level role bindings
kyacl role grant <name> <owner|admin|writer|reader>
kyacl role revoke <name>
kyacl role list [<name>]

# Key-level overrides
kyacl role grant <name> <role> --key "secrets\..*" --allow read,write
kyacl role grant <name> <role> --key "secrets\..*" --deny delete

# Identity introspection
kyacl whoami                     # resolves KYCLI_TOKEN/--token -> principal + effective role

# Unchanged (legacy / global kill switch, still works with RBAC on or off)
kyacl readonly on|off|status
kyacl key set|get|clear [value]
```

New auth inputs, mirroring the existing `--access-key` / `KYCLI_ACCESS_KEY`
parsing block in `kycli/cli.py` (`main()`, around the `access_key` flag
extraction):

```bash
export KYCLI_TOKEN=<token>
kyg secrets.db_password --token <token>
```

## 7. Embedded / Library API (`Kycore`)

For callers using `Kycore` directly (see `docs/QUEUES_STACKS.md`'s Python
API section for the existing pattern):

```python
from kycli import Kycore

kv = Kycore("workspace.db")
kv.enable_rbac()
token = kv.create_principal("ci-bot")        # returns the token once
kv.grant_role("ci-bot", "writer")
kv.grant_key_acl("ci-bot", r"secrets\..*", deny=["read"])

kv.save("status", "ok", token=token)         # checked against ci-bot's effective role
kv.check_permission(token, "delete", key="status")  # -> bool, for pre-flight checks
```

## 8. Security Considerations

- **Token storage**: hashed with the same PBKDF2-HMAC-SHA256 KDF already
  used in `kycli/core/security.pyx`, never stored or logged in plaintext.
  Shown exactly once on `kyacl user add` / `rotate-token`.
- **Authorization vs. confidentiality are independent**: a `reader` granted
  `read` on an encrypted key still only gets `[ENCRYPTED: Provide a master
  key...]` without the master key. RBAC governs *whether* a value is
  returned at all; the master key governs whether it's *decrypted*. Document
  this distinction prominently so users don't conflate the two.
- **Denial messages stay generic** ("permission denied") rather than
  distinguishing "key doesn't exist" from "key exists but you can't read
  it," to avoid leaking keyspace contents to unauthorized principals.
- **Threat model boundary**: anyone with raw filesystem read access to the
  `.db` file can bypass RBAC entirely (it's enforced in the engine, not the
  filesystem). This is explicitly out of scope — same boundary the existing
  encryption-at-rest feature already documents.
- **Audit trail**: every grant, revoke, enable/disable, and permission
  denial is written through the existing `AuditManager` and
  `logging_utils.py` so misuse is traceable after the fact.

## 9. Backward Compatibility & Migration

- RBAC is **off by default** for every workspace (`rbac_enabled = 0`).
  Nothing changes until `kyacl enable` is run — existing scripts, CI jobs,
  and the current `access_key`/`readonly` flags are unaffected.
- On `kyacl enable`: if the workspace has an existing `access_key` set, a
  principal is auto-bootstrapped from it and granted `owner`, so the current
  key-holder doesn't lock themselves out. Otherwise, `kyacl enable` requires
  `kyacl user add --self owner` first.
- `kyacl readonly` keeps its global kill-switch precedence over *everything*
  (§5, step 1), with or without RBAC enabled — same semantics as today.
- `kyacl key` (the shared-secret mechanism) is untouched and keeps working
  standalone; it's simply superseded in capability once RBAC is enabled for
  a given workspace.

## 10. Phased Implementation Plan

### Phase A — Storage & schema foundation
- Add `principals`, `workspace_roles`, `key_acl` tables to
  `kycli/core/storage.pyx`, created lazily (same pattern as
  `workspace_meta`).
- Add `rbac_enabled` to the `workspace_meta` flag set.
- Add token-hashing helpers to `kycli/core/security.pyx` (reuse the
  existing PBKDF2HMAC construction, new salt constant).
- Tests: schema creation/idempotency, concurrent-write safety under the
  existing `flock` + atomic-rename model (`tests/core/`).

### Phase B — Core policy engine
- New `AccessControlManager` (start in pure Python inside `storage.pyx`;
  promote to its own `.pyx` only if profiling shows it matters).
- `resolve_principal(token)`, `effective_role(principal)`,
  `check(principal, verb, key=None)`, reusing the existing `re.search`
  pattern-matching convention from `list_keys` for `key_pattern`.
- Replace `_ensure_write_allowed()` with a generalized `_ensure_allowed(verb,
  key)` called from every public read **and** write method (`get`, `save`,
  `delete`, `list_keys`, `push`, `pop`, `peek`, `patch`, append/collection
  ops), falling back to the legacy check when `rbac_enabled = 0`.
- Tests: full permission matrix (role × verb), key-pattern precedence,
  deny-overrides-allow, legacy fallback parity.

### Phase C — CLI surface
- Extend the `kyacl` dispatch block in `kycli/cli.py` (`cmd in ["kyacl"]`):
  `enable/disable/status`, `user add/list/disable/rotate-token`,
  `role grant/revoke/list`, `whoami`.
- Add `--token` flag and `KYCLI_TOKEN` env var parsing, mirroring the
  existing `--access-key`/`KYCLI_ACCESS_KEY` block in `main()`.
- Update `kyh` / `get_help_text()`.

### Phase D — Audit & observability
- Route grants/revokes/enable/disable and every denial through
  `AuditManager` (`kycli/core/audit.pyx`) and `logging_utils.py`.
- `kystats` gains an RBAC summary line (on/off, principal count).

### Phase E — Docs, tests, release
- Finalize this doc with worked examples; add a "Security & Compliance"
  entry to `README.md` once shipped (not before — keep docs honest about
  what's implemented).
- Integration tests in the style of `tests/test_cli_roadmap.py` and
  `tests/core/test_roadmap_features.py`.
- Migration test: workspace with a pre-existing `access_key` → `kyacl
  enable` → confirm the key-holder is bootstrapped as `owner`.
- Regression test: a workspace that never calls `kyacl enable` behaves
  byte-for-byte like the pre-RBAC release.
- CHANGELOG entry; version bump per existing release process.

### Phase F — Stretch (future release, not v0.5.0)
- Custom roles (arbitrary verb subsets), e.g. `kyacl role create analyst
  --allow read --key "reports\..*"`.
- Principal groups (grant a role to a group, add/remove members).
- Default key-pattern policies applied workspace-wide without per-principal
  rules.

## 11. Open Questions

- **Per-workspace vs. global principals**: this plan recommends
  per-workspace (consistent with the existing file-per-workspace isolation
  model) over a shared global identity store. Revisit if users need one
  identity across many workspaces without re-creating it each time.
- **Pattern syntax for `key_acl.key_pattern`**: recommend reusing the
  existing `re.search` regex convention from `list_keys`/`kyl` rather than
  introducing glob syntax, for consistency — confirm before Phase B.
- **`kydrop` and raw file deletion**: `owner`-only at the engine level, but
  `kycli` cannot stop someone from `rm`-ing the `.db` file directly with OS
  permissions; this stays documented as out of scope (§2, §8).

## 12. Remaining Gaps (tracked for Phase F+)

- No principal groups.
- No custom/arbitrary roles.
- No workspace-wide default key policies independent of a principal.
