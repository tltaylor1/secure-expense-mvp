# Project Standards

-------------------------------------------------------------------------------

## Stack

- Python 3.14, FastAPI, PostgreSQL under Docker Compose, pytest
- SQLite serves the zero-setup quick start and the test suite, through the same ORM and models
- Dependencies pinned in requirements.txt
- Virtual environment in `venv/` (never committed)

-------------------------------------------------------------------------------

## Workflow

- Commits the agent co-authors carry a Co-Authored-By trailer naming the exact model, id included, so the history itself records which tool helped produce what.

- Commit early and in small units. Each commit does one thing and has a clear message. Commit the moment a unit works, before starting the next one; when in doubt, commit. A build session should produce many small commits, not a few large ones.
- Never push without my explicit approval.
- Never force push, rewrite history, or delete branches without asking first.
- Before adding any package: verify on PyPI that the name resolves to the canonical project, and record it in the README supply chain table with version, source, and role.
- Dependencies go in requirements.in (or requirements-dev.in), compiled with pip-compile --generate-hashes, installed with --require-hashes. Never pip install a package directly into the project environment.
- After any dependency change: recompile, regenerate sbom.json (cyclonedx-py), and run pip-audit.

-------------------------------------------------------------------------------

## Security requirements

- No secrets in the repository, ever. Configuration and credentials live in `.env`, which is gitignored. Provide a `.env.example` with placeholder values instead.
- No credential-shaped strings anywhere in any tracked file or commit, including demo, test, and sample passwords. Demo credentials come from `.env` and fail fast when missing; test suites generate theirs per run. A reader must never have to decide whether a password-looking string matters.
- Review the full diff for secrets and credentials before every commit. Before the final push, scan the entire git history for secrets, not just the current files.
- Database access uses the ORM or parameterized queries only. Never build SQL from string concatenation or f-strings.
- Every API endpoint validates input through Pydantic models. No raw dict handling.
- Authorization on every object: any endpoint that reads or writes a record verifies the requester is allowed to access that specific record. Role-restricted endpoints verify the role. A valid ID is never sufficient on its own.
- Separate Pydantic models for input and output. Input models accept only the fields a client may set (never role or ownership fields). Every route declares a response_model so internal fields and password hashes cannot leak.
- Input constraints, not just types: string fields carry max lengths, numeric fields carry ranges, list endpoints paginate with an enforced maximum page size.
- If the application has users, hash passwords with bcrypt (the pyca/bcrypt package, used directly). Never store, log, or return passwords in plain text.
- Error responses to clients are generic. Stack traces, database errors, and internal details go to server logs only.
- Log security-relevant events: logins, failed logins, and denied access attempts. Never log passwords, tokens, or full request bodies.
- Never commit a database file. Provide a seed script that recreates schema and sample data. Sample data is obviously fake and never resembles real records.
- CORS: no wildcard origins combined with credentials.
- Frontend inserts API data into the page as text (textContent), never as HTML (innerHTML), because any user-supplied value rendered in another user's browser is an XSS surface.
- Auth tokens travel in a request header, never a cookie, to keep CSRF out of scope by design.
- Users cannot approve or authorize their own records, whatever their role.
- No debug mode, verbose stack traces, or commented-out credentials in the final state.
- Authentication tokens expire. Never issue non-expiring tokens.
- Token verification pins its accepted algorithms explicitly.
- Authentication failures return one generic error for every cause. Never reveal whether an account exists.
- The app fails at startup if a required secret is missing. Never ship a default secret as a fallback.
- Secret scanner false positives get an inline allowlist marker on the flagged line, with a note saying why. Never bypass the hook to clear a finding.
- Secret scanning runs as a pre-commit hook (gitleaks). Never bypass hooks with --no-verify. The hook is a net, not the control: secrets belong in .env regardless.
- Run pip-audit against pinned dependencies and bandit against application code before submission. Resolve or document any findings.
- Records that change state carry their own attribution: who made the change and when, as columns on the record, in addition to the audit log. A row must answer "who did this" without a join.
- Every credential the app issues gets both halves documented: how it expires, and how it is revoked. If individual revocation does not exist (stateless tokens), the README says so and states the accepted trade.
- Where an action and its audit write are not in one transaction, the README records that the trail is best-effort and what a gap would look like.
- HTTP status semantics: missing or invalid credentials return 401; valid identity with insufficient authority returns 403. Check what the framework returns by default; do not assume.
- The README states the cross-origin (CORS) posture even when the answer is "no cross-origin access on purpose."
- Account-lifecycle features that deliberately do not exist (signup, password reset, email change) are listed in the README as attack-surface decisions. If signup exists, enforce a minimum password length and note breached-password checking as production hardening.

-------------------------------------------------------------------------------

## Documentation

- Write in plain language, following the Federal Plain Language Guidelines (plainlanguage.gov): common words, short sentences, present tense, no idioms. If a plain phrase can replace a term of art, use the plain phrase.
- Define every acronym at its first use, even common ones. A reader should never need outside knowledge to parse a sentence.
- Separate major document sections with horizontal rules and open long documents with a contents line. Documents get skimmed before they get read; help the skimmer.

- The README explains the architecture: the components, how a request flows through them, and where each security control sits in that flow.
- Every non-obvious choice is recorded with its why, at the point of decision: design choices in the README decisions section, code-level choices as intent comments.
- Write documentation to answer a reviewer's questions before they are asked: why this stack, why this control and not another, what was rejected, what breaks without it.
- When a design question is asked and answered during the build, the answer goes into the README, not just the conversation.
- Anything deliberately out of scope is listed with the reason it was cut.

-------------------------------------------------------------------------------

## Definition of done

- README covers: what the app does, setup steps, how to run, how to run tests, design decisions, and known limitations.
- README includes a security section: a short threat model, each implemented control and the threat it addresses, what is deliberately out of scope and why, and what would be hardened next (for example rate limiting, HTTPS, security headers).
- Comments explain why a decision was made only where the reason is not obvious from the code. No comments that restate what the code does.
- Every module opens with a short docstring saying what the file is and where it sits in the request flow, written so the code can be walked through aloud file by file. Security decision points always carry their why at the line.
- API endpoints have pytest coverage for the success path and at least one failure path.
- Tests include the security paths: one proving a user cannot access another user's record, and one proving invalid input is rejected.
- The app runs from a fresh clone using only the README instructions.
- Before submission, walk every default the framework chose on our behalf (status codes, error bodies, CORS, headers, docs pages) and either change it deliberately or write a line recording that the default is the decision. Secure by accident and secure on purpose look identical in code; only the decision record tells them apart.
