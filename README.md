# Expense Management MVP

A small expense submission and approval tool, built as an MVP (minimum viable product: the smallest version that genuinely works end to end). Employees submit expenses and track their status. Managers review, approve, or reject them.

The build is deliberately small and security-first: every design decision below is recorded with the threat or failure it addresses, so the code and its reasoning can be reviewed together.

**Contents:** [Setup and run](#setup-and-run) · [Repository map](#repository-map) · [Architecture](#architecture) · [Design decisions](#design-decisions) · [Production path](#production-path) · [Security in the development lifecycle](#security-in-the-development-lifecycle) · [AI-assisted development](#ai-assisted-development)

-------------------------------------------------------------------------------

## Setup and run

Two ways to run. The full stack runs PostgreSQL and the app in containers; the quick start runs the app alone against SQLite with nothing to install but Python.

**Full stack (Docker Compose):**

```bash
cp .env.example .env    # set SECRET_KEY and POSTGRES_PASSWORD as the comments describe
docker compose up --build -d
docker compose run --rm app python seed.py
```

**Quick start (SQLite, no containers).** Requires Python 3.11 or newer; developed and tested on 3.14.

```bash
python3 -m venv venv
venv/bin/python -m pip install --require-hashes -r requirements.txt
cp .env.example .env    # then set SECRET_KEY as the file's comment describes
venv/bin/python seed.py
venv/bin/uvicorn app.main:app --port 8000
```

On Windows, replace `venv/bin/` with `venv\Scripts\`, and always run pip as
`python -m pip`: the dev requirements pin pip itself, and `pip.exe` cannot
modify itself on Windows.

Open http://127.0.0.1:8000. The seed script creates three demo accounts, all sharing the DEMO_PASSWORD you set in `.env`. No password is written in this repository, demo or otherwise; the seed script refuses to run without one, the same fail-fast rule the signing secret follows.

| Email | Role |
|---|---|
| alice@example.com | employee |
| bob@example.com | employee |
| mona@example.com | manager |

Interactive API documentation is at `/docs`. To run the tests and scanners:

```bash
venv/Scripts/python -m pip install --require-hashes -r requirements-dev.txt
venv/Scripts/pytest -q
venv/Scripts/bandit -r app -q
venv/Scripts/pip-audit -r requirements.txt --disable-pip
```

-------------------------------------------------------------------------------

## Repository map

| File | Role |
|---|---|
| `app/main.py` | All routes; the trust boundary every request passes through |
| `app/auth.py` | Passwords, tokens, and the identity and role dependencies |
| `app/models.py` | The four tables; schema decisions as structure |
| `app/schemas.py` | Input and output models: what clients may send and may see |
| `app/database.py` | The single door to the database; parameterization is structural |
| `app/audit.py` | The one entry point for audit rows |
| `app/config.py` | Loads `.env`; the app refuses to start without its secret |
| `frontend/` | The interface: one page, its stylesheet (light and dark), and its script; values rendered as text only |
| `tests/` | The attack checklist run on every change |
| `seed.py` | Rebuilds the database with sample data; committed instead of a database file |
| `requirements*.in` / `requirements*.txt` | Chosen packages, and the hash-pinned tree that actually installs |
| `sbom.json` | Software bill of materials: the dependency inventory |
| `Dockerfile` | The deployable artifact: digest-pinned base, hash-pinned installs, non-root user |
| `docker-compose.yml` | PostgreSQL plus the app; the database is not host-exposed |
| `.dockerignore` | Keeps `.env`, local state, and noise out of the build context |
| `.pre-commit-config.yaml` | Secret scanning as a commit-blocking mechanism |
| `.github/workflows/ci.yml` | Tests and scanners on every push |
| `CLAUDE.md` | The standards the AI agent is held to |
| `.env.example` | Documents required configuration without containing it |

-------------------------------------------------------------------------------

## Architecture

Three parts, with all security enforced in the middle one:

- **PostgreSQL database** under Docker Compose, reachable only on the compose network; the host exposes no database port. A SQLite fallback serves the zero-setup quick start and the test suite. Only the backend touches either.
- **FastAPI backend.** The trust boundary. Every request passes the same gates in order: token check (who are you), input validation through a typed Pydantic model (is this request sane), authorization (may you touch this specific record), the action itself through the ORM (object-relational mapper, the library that turns Python objects into safe, parameterized database queries), an audit log write, and a response filtered through an explicit output model.
- **Frontend.** One HTML page with JavaScript that calls the backend's API (application programming interface: the set of requests the backend answers). It contains no security logic on purpose: a browser page is fully under the user's control, so anything enforced there is decoration. The page hides buttons a role cannot use; the server enforces the rule.

Each gate exists because of a specific failure: forged identity (token), hostile input (validation), a valid user reaching another user's data (authorization), injection (ORM parameterization), uninvestigable incidents (audit log), and internal data leaking (output model). In classic security terms the gates implement AAA: authentication (who you are), authorization (what you may do), and accounting (a record of what you did).

-------------------------------------------------------------------------------

## Design decisions

### Platform

- **FastAPI**, because typed Pydantic validation is the framework's default path, making server-side input validation the normal case rather than an add-on.
- **PostgreSQL through the ORM.** All access goes through the ORM, which parameterizes every query and removes SQL injection (attacker-supplied text becoming database commands) as a bug class rather than defending against it case by case. The build started on SQLite for zero setup; it moved to PostgreSQL when the app gained a container runtime, because Compose dissolved the setup cost and a production-shaped database exercises real roles and constraint enforcement. SQLite remains the quick-start and test path, through the same ORM and the same models, so the choice of engine never touches application code.
- **The database is not host-reachable.** The compose file publishes no database port; only the app container can connect. One fewer listening service is one fewer attack surface.
- **REST rather than GraphQL**, chosen for the authorization surface. In REST each endpoint is one operation with its own explicit ownership and role check, so the checks are countable and testable. GraphQL lets a client compose its own query graph, which moves authorization down to every field and resolver and adds query depth and complexity abuse as a denial-of-service surface. For a small build reviewed for security, the smaller and more explicit surface wins.
- Both trade scale for correctness in a small build. That trade is deliberate; the [production path](#production-path) records what changes when it no longer holds.

### Data model

- **Money is integer cents.** Binary floating point cannot represent most decimal amounts, so float math corrupts currency silently. Dollars appear only at display time.
- **Status is a constrained value** with exactly three states: pending, approved, rejected. Free-text status drifts (Approved, approved, APPROVED) and breaks filtering and authorization logic.
- **The audit log is a table.** Logins, failed logins, approvals, rejections, and denied access attempts each write who, what, and when. Without that record, an incident cannot be investigated. Passwords and tokens are never logged.
- **State changes carry their own attribution.** A decided expense stores who decided it and when as columns on the row, in addition to the audit log entry. The record answers "who did this" by itself; the audit trail is the independent second copy, not the only copy.
- **The audit write is atomic with the action.** Each state change and its audit row commit in one transaction, so a change cannot exist without its trail, and the trail cannot describe a change that never happened.
- **Data is minimized by policy, not accident.** The app stores email, role, password hash, and expense records, and nothing else: no names, no payment instruments, no free-form personal data. What is never stored cannot be breached, so the sensitive surface is bounded on purpose.

### Authentication

- **Passwords are hashed with bcrypt, which salts automatically.** A salt is a random value mixed into every hash, so two identical passwords produce different hashes and precomputed lookup tables are useless. bcrypt is also deliberately slow by design (an adjustable work factor), which turns a bulk password-cracking run from hours into years. Passwords are never stored, logged, or returned in any form.
- **Login failure is one generic error.** Wrong email and wrong password return the same message and status. Distinct errors would let an attacker enumerate which emails have accounts.
- **Token verification pins its algorithm.** The decoder accepts exactly one signing scheme. Without pinning, a forged token can claim a weaker or null scheme and skip verification entirely, a well-known real-world bypass.
- **The app refuses to start without its signing secret.** The tempting alternative, a hardcoded default, becomes the production secret the day someone forgets to set the real one. Failing at startup is loud; a default is silent.
- **Both login outcomes hit the audit trail.** Success and failure each write an attributed, timestamped row. In classic terms this is accountability and supports non-repudiation: an actor cannot later deny what the trail shows.
- **Login inputs are size-limited** (email 254 characters, password 200). Unbounded fields let a client submit huge values that the server must hash or store, a cheap way to burn resources.
- **The browser holds the token in memory, not in localStorage.** Stored tokens survive page refreshes, but any script that ever runs in the page can read storage, which makes it the standard theft target after an injection. Memory-only means a refresh requires logging in again; that inconvenience is accepted deliberately.
- **Expiry is the entire revocation mechanism, and that is stated rather than hidden.** These tokens are stateless: the server keeps no session list, so no single token can be cancelled before its expiry. The accepted trade is a short lifetime plus one global kill switch, rotating the signing secret, which invalidates every session at once. Per-token revocation requires server-side session state and sits in the production path.
- **Accounts have no self-service lifecycle, as an attack-surface decision.** There is no signup, no password reset, and no email change; users exist only through the seed script. Each absent feature is an absent attack surface: signup brings abuse and weak passwords, reset brings account takeover through the recovery channel, email change brings both. A real deployment adds them deliberately, with breached-password checking noted as hardening.

### Access control

- **Authorization is checked per object, not per login.** The most common API vulnerability is a logged-in user requesting someone else's record by changing an id. Every endpoint that touches a record verifies the requester owns it or holds the required role. A valid id is never sufficient.
- **For list endpoints, the filter is the authorization.** An employee's query is built with their token's user id in the WHERE clause, so rows belonging to others cannot appear in the result at all. There is no "fetch everything, then hide some" step to get wrong.
- **A decided expense is immutable.** Approve or reject works once; a second decision returns a conflict error. Without that rule, an approval could be quietly changed later, and the audit trail would no longer show a clear sequence of events.
- **Input and output are separate models.** An input model that accepts all fields lets a client set what it should not control (role, owner, status). An output model that mirrors the database leaks internal fields. Anything not explicitly listed is rejected inbound and stripped outbound.
- **Tokens expire and are validated on every request.** A leaked token that never expires grants permanent access.
- **Managers cannot approve their own expenses.** Approval authority over your own spending defeats the point of approval. The server rejects self-approval regardless of role. This is separation of duties: no single actor completes a sensitive transaction alone.

### User content and abuse

- **Stored cross-site scripting (XSS) is treated as this app's second injection surface.** An expense description is text written by one user and rendered in another user's browser, exactly where script injection escalates employee access into a manager's session. The frontend inserts all API data as text, never as HTML, and production adds a Content Security Policy (a browser rule limiting what a page may run).
- **The token travels in a request header, not a cookie.** Browsers attach cookies automatically to any request aimed at a site, which is what makes cross-site request forgery (CSRF) work. A header that the page's own code must add defeats that attack class without needing dedicated CSRF defenses.
- **Inputs are bounded, not just typed.** String fields carry length limits, amounts carry ranges, and list endpoints paginate with a capped page size, so a single client cannot store or request unbounded data. Request-rate limiting itself is in the production path.
- **Receipt uploads are validated three ways before they touch disk.** The declared type must be on a short allowlist (PNG, JPEG, PDF), the file's own first bytes must match that declaration, because the declared type is client input, and a size cap bounds what one upload can cost. Files store under server-generated names; the client's filename is display data, never a path.
- **The monthly CSV export reuses the strongest patterns in the app.** Authorization is the query: an employee's report is built filtered to their own rows, so no one else's data can appear in the file. Every text cell that starts with a formula character is apostrophe-prefixed, because a cell beginning with equals, plus, minus, or at-sign executes when the file opens in a spreadsheet app; this is spreadsheet formula injection, the injection surface people forget CSV has. The export is audited, the filename is server-generated, and the token travels in a header, never a URL.
- **Session expiry is announced, not just enforced.** The login response states its lifetime, the page shows a countdown and returns to login when it ends, and any 401 mid-session does the same. Display is convenience; the server enforces expiry regardless of what the page shows.
- **The receipt download is a sensitive read and is treated like one.** It passes the same object-level check as the record it belongs to, owner or manager only; every successful read is written to the audit trail, because who looked at evidence matters as much as who changed it; the download filename is server-generated so no user text reaches a response header; and the response carries nosniff so the browser honors the declared type instead of guessing.
- **The cross-origin posture is: none, on purpose.** The backend serves the frontend itself, so every legitimate request is same-origin, and the app configures no CORS (cross-origin resource sharing) headers at all. Browsers therefore refuse scripts on other origins access to this API by default. Stating this matters because the dangerous configuration, wildcard origins combined with credentials, usually arrives silently through a copied middleware block; here the absence is the decision.

### Framework defaults, walked

Secure by accident and secure on purpose look identical in code, so every default in the serving path was inspected and either changed or accepted on record:

- **Missing credentials returned 403 by default; changed.** The framework treats an absent Authorization header as 403. That conflates no identity with insufficient authority, so the app returns 401 with a WWW-Authenticate header, and 403 is reserved for a valid identity lacking the required role.
- **Interactive API documentation stays enabled; accepted.** The app runs locally and `/docs` lets a reviewer exercise the API directly. A public deployment would disable or gate it.
- **Validation errors return 422 with field detail, echoing the offending input; accepted.** Useful locally and to honest clients. The echo returns only what the client itself sent, never server state, so it leaks nothing the sender did not already have.
- **The server identifies itself in a response header; accepted locally.** Version disclosure is reconnaissance help in production, where stripping it belongs to the reverse proxy in front.
- **Error bodies are short JSON detail strings; accepted.** No stack traces or internals reach a client; those go to server logs.
- **Served files carried no Cache-Control header; changed.** Without one, browsers cache the page heuristically and keep showing a stale copy after a deploy, which was observed live against a rebuilt container. The page and static files now send no-cache, meaning store but revalidate: an etag round trip returns 304 while content is unchanged and fresh content the request after it changes.

### Secrets

- **Three layers, ordered by strength.** Architecture: secrets live only in the gitignored `.env`, never in code, with `.env.example` documenting the variables. Enforcement: gitleaks runs as a pre-commit hook and blocks commits containing secret patterns; bypassing hooks is prohibited. Review: every diff is read before commit, and the full history is scanned before submission.
- **The scanner is a net, not the control.** Testing it with planted fake credentials showed it catches high-entropy tokens and keyword-adjacent secrets, but misses low-entropy passwords and credentials embedded in database URLs. Keeping secrets out of code entirely is the control; the hook catches slips.
- **False positives get documented, never bypassed.** The scanner correctly flagged the placeholder in `.env.example`. The exception is an inline `gitleaks:allow` marker on that one line: a visible risk acceptance at the exact spot, while the hook keeps guarding everything else. Skipping the hook for one commit would have silenced it for all findings, not just this one.
- **Static analysis before submission:** `bandit` on application code, `pip-audit` on pinned dependencies. Findings are resolved or documented.

### Supply chain

Dependencies are treated as the part of the codebase nobody wrote here, which is why each one was verified rather than assumed.

- **Every package was checked against PyPI, Python's public package registry, before adoption:** the name resolves to the canonical project, not a lookalike. Runtime dependencies:

  | Package | Version | Canonical source | Role |
  |---|---|---|---|
  | fastapi | 0.140.13 | github.com/fastapi/fastapi | web framework |
  | uvicorn | 0.51.0 | github.com/Kludex/uvicorn | application server |
  | SQLAlchemy | 2.0.51 | sqlalchemy.org | ORM |
  | bcrypt | 5.0.0 | github.com/pyca/bcrypt | password hashing |
  | PyJWT | 2.13.0 | github.com/jpadilla/pyjwt | login tokens |

  Development and audit tooling (pytest 9.1.1, httpx 0.28.1, bandit 1.9.4, pip-audit 2.10.1, cyclonedx-bom 7.3.1) verified the same way and isolated in `requirements-dev.txt`.
- **One package was rejected on provenance:** passlib, the common recommendation for password hashing, has had no release since 2020 and breaks against maintained bcrypt versions. Password hashing uses `bcrypt` directly, maintained by the Python Cryptographic Authority.
- **Installs are hash-pinned.** `requirements.in` holds the chosen packages; `pip-compile --generate-hashes` resolves the full tree into `requirements.txt` with a SHA-256 hash (a cryptographic fingerprint that changes if a single byte changes) per artifact, and installs run `--require-hashes`, so a tampered or substituted package fails to install instead of running. Hashes verify *what* was fetched. The maturing standard for proving *how* an artifact was built is SLSA (Supply-chain Levels for Software Artifacts) provenance attestation, which this workflow would consume once registry tooling stabilizes.
- **The inventory is a document, not a memory.** `sbom.json` is a software bill of materials (SBOM) in the CycloneDX format, covering the full dependency tree and regenerated when dependencies change.
- **The tree is audited.** `pip-audit` runs against the pinned set (clean at time of writing). Any future finding gets triaged by whether it is actually being exploited, using the Known Exploited Vulnerabilities catalog from CISA (the US Cybersecurity and Infrastructure Security Agency) to decide urgency, rather than severity score alone. At organizational scale that triage is published as VEX (Vulnerability Exploitability eXchange) statements alongside the SBOM, the standard format for saying which findings do and do not affect a product.
- **Licenses are read, not assumed.** The SBOM doubles as the legal inventory: the full tree is MIT, Apache, BSD, and similar permissive licenses, with one dev tool under the GNU Lesser General Public License, used unmodified.

### Documentation

- **These documents follow the Federal Plain Language Guidelines** (plainlanguage.gov): common words, short sentences, present tense, and every acronym defined at its first use. The reasoning is a security argument, not a style preference: a control nobody can parse is a control nobody can challenge, and review quality depends on the reviewer understanding every sentence the first time.
- **Major sections are separated by horizontal rules.** Long operational documents get skimmed before they get read, the way an administrator skims a manual page: find the band you need, then read closely. The dividers work both rendered and as plain text in an editor.

-------------------------------------------------------------------------------

## Production path

Decisions a real deployment adds. Each is deferred here for the same reason: it attaches to deployment infrastructure that a local, single-process build does not have. Recording them keeps the deferral deliberate rather than forgotten.

### Network

- **Private placement.** The app and database sit inside a VPC (virtual private cloud, an isolated network) with nothing internet-facing except a gateway or load balancer that terminates TLS (transport layer security, the encryption behind HTTPS). The database accepts connections only from the app.
- **Private endpoints for dependencies.** Traffic to cloud services stays on the provider's network instead of crossing the public internet.
- **East-west controls.** East-west means service-to-service traffic inside the network, as opposed to north-south traffic entering or leaving it. In a multi-service deployment, services authenticate to each other, for example with mutual TLS, where both sides prove their identity with certificates. Then one compromised component cannot freely reach the rest. This MVP is a single process, so no east-west traffic exists yet; this entry is the reminder that the boundary appears the moment a second service does.

### Observability

- **Structured logs, half implemented here on purpose.** Every audit event already emits as a structured JSON line on standard output, the form a container runtime or log shipper collects, with the database table as the authoritative record. Production adds the shipping itself: the pipeline that moves those lines to a SIEM (security information and event management system, the central platform where logs from many sources are correlated and alerted on).
- **Activity and health metrics.** Request rates, error rates, and latency per endpoint, plus alerting on security signals such as spikes in failed logins or denied access attempts.

### Detection and response

The controls above prevent; this answers *how would we know, and what would we do* when prevention fails.

- **Every control emits a signal.** The audit table already captures the detection-relevant events. The queries a responder would run exist today: failed logins per account per hour (catches attackers replaying stolen password lists), denied access attempts per user (catches someone probing for records they do not own), approvals per approver (catches insider misuse).
- **Production turns those queries into alerts** with thresholds and an owner, so detection becomes an alert to someone on call rather than a forensic discovery weeks later.
- **First-hour playbook, written before it is needed:** rotate the token-signing secret (which invalidates every active session at once), reset affected credentials, then reconstruct the actor's full activity from the audit trail. The secret living in one environment variable is what makes step one a rotation instead of a redeploy.

### Hardening

- Rate limiting on authentication and write endpoints, TLS everywhere, a managed database with migrations, a secrets manager instead of `.env`, and CI (continuous integration, the pipeline that runs checks automatically on every push) enforcing the same scanners this repo runs by hand.

-------------------------------------------------------------------------------

## Security in the development lifecycle

Every control sits at the earliest stage where it has something to inspect: threat decisions before code, standards constraining the code generator, scanning at commit and install time, gates in CI. Scans that do not run here are skipped by decision, with the reason recorded, because an undocumented skipped scan is a gap while a documented one is a choice. The rows marked skipped or deferred are, formally, a risk register: each is an accepted risk with its rationale, reviewable and reversible.

Coverage was audited against the API Top 10 from OWASP (the Open Worldwide Application Security Project), the standard list of the most common API security failures. The systematic version of that audit is OWASP's Application Security Verification Standard (ASVS), the itemized checklist this table would map to at organizational scale.

| Control | Status | Reason |
|---|---|---|
| Threat-informed design decisions | Done before code | Design is the cheapest stage to fix anything |
| Codified standards for the code generator ([CLAUDE.md](CLAUDE.md)) | In force | Constrains generation itself, the earliest possible stage |
| Secret scanning (gitleaks pre-commit hook) | Runs, fails closed | History is permanent; enforcement instead of memory |
| Static analysis of first-party code, known as SAST (`bandit`) | At milestones and submission | Code written at speed needs a second reader |
| Dependency vulnerability scanning, known as SCA (`pip-audit`), with the SBOM | On every dependency change | Dependencies are code nobody here wrote |
| Hash-verified installs | Every install | A substituted artifact fails instead of running |
| License inventory (from the SBOM) | Done | The legal half of supply chain |
| Security-path tests (pytest) | With the test suite | Prove controls hold under hostile input |
| CI pipeline running the gates above | Added with the test suite | Removes the human from having to remember |
| Scanning the running app, known as DAST (OWASP ZAP) | Deferred to CI against a deployed instance | Six known endpoints with targeted attack-path tests; a crawler adds setup cost, not coverage, at this size |
| Fuzzing (bombarding inputs with malformed random data) | Skipped | Typed schema validation constrains the input space; fuzzing pays off on parsers and file formats, not typed create-read-update-delete endpoints |
| Infrastructure-as-code scanning (checkov) | Not applicable | No infrastructure code exists; mandatory the day it does |
| Container image scanning (trivy) | In CI on every push | Fails the build on any high or critical finding that has a shipped fix, because those are actionable today. Findings the base distribution has not fixed yet are tracked rather than blocking; rebuilding against a newer base digest picks their fixes up when they ship |
| Commit signing | Skipped | Single author on an account-controlled private remote; a production posture item |

-------------------------------------------------------------------------------

## Roadmap

This application is complete on purpose. It stays a small, fully explained reference: one page, six endpoints, every control mapped to the threat it answers. Feature growth would dilute exactly the property it exists to demonstrate.

Planned additions:

- **Dependency updates through pull requests** (Dependabot), tested by the same CI gates as code. Configured in `.github/dependabot.yml`; the update policy is described in the supply chain section.
- **On becoming public:** platform secret scanning with push protection, CodeQL analysis, and an OpenSSF Scorecard run, each free for public repositories.
- **The production path items** above, only if this app ever actually deploys; they are recorded so the deferral stays deliberate.

The larger build this application deliberately does not attempt, container orchestration on Kubernetes, cloud infrastructure as code, and a security-gated deployment pipeline, is the subject of a companion reference implementation built in phases, where each of those steps gets the same treatment: decided, threat-modeled, and documented before built.

Built with an AI coding agent under my direction and review. The standards the agent follows are in [CLAUDE.md](CLAUDE.md). Commits the agent co-authored say so in a Co-Authored-By trailer naming the exact model (Claude Fable 5, model id claude-fable-5), so the provenance of the code is readable from the history the same way the provenance of the dependencies is readable from the supply chain record. The direction that most shaped the result:

- **Enforcement over intention.** The agent's first draft of project standards was a list of rules to follow. I required mechanisms that cannot be forgotten: a pre-commit hook that blocks secrets, static analysis gates, and scripted verification in place of eyeballing. Asking "what else in this list is a hope rather than a mechanism" surfaced several more gaps.
- **Nothing is trusted untested.** Before relying on the secret scanner, we planted fake credentials to prove it fires. It passed one through. Diagnosing that miss produced the documented picture of what the scanner does and does not catch, and the three-layer design above.
- **Decisions are written down where they happen.** Explanations that existed only in conversation were lost to review, so I required every design answer to be captured in this document at the moment it is made. This section, and the ones above it, are the result.
- **Docs are checked against reality.** When this decisions record drifted behind the decisions actually made, it got caught in review and corrected. The record stays synchronized with the build, not written after it.
- **The build environment is part of the security posture.** The agent works under per-action permission gates with no standing write approvals, every push requires explicit human sign-off, and the supply-chain controls above exist because the reviewer stopped an install to ask "did you check these?" before the first package landed. The [supply chain](#supply-chain) section is the answer that question produced.
- **Coverage is audited against a standard, not a feeling.** Reviewing the decisions against the OWASP Top 10 found a class the agent had not addressed: stored cross-site scripting through user content, along with request forgery handling and self-approval. The lesson generalized: completeness comes from checking against an external list, not from the generator of the list.
- **Language is held to a standard too.** The documentation follows the Federal Plain Language Guidelines by direction, and review caught undefined acronyms and insider phrasing creeping back in. The correction became a standing writing rule rather than a one-time fix, because a document the reviewer cannot parse on first read is a finding like any other.
