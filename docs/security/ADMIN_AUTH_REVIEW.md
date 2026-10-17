# Administrator authentication engineering review

T-015 uses a separate administrator identity and session realm. Consumer and merchant identities
are not queried by the admin authentication store and cannot be converted into admin sessions.

Password verification uses scrypt with a per-credential salt and constant-time comparison. A valid
password creates only a short-lived, single-use MFA challenge. It never creates a session. TOTP is
verified in a bounded time window using an encrypted-at-rest secret supplied through a runtime
cipher interface. Session and CSRF values are random, returned once, and stored only as SHA-256
digests. Scopes are copied from the administrator identity at session creation.

Password and MFA failures return generic errors. Password attempts trigger configurable lockout;
MFA challenges have configurable expiry and attempt caps. Recovery codes are stored as globally
unique hashes, require the successful password stage, and are consumed atomically before a session
is created. Sensitive success, failure, recovery, and session events are sent to the audit sink.

Threat tests cover password-only bypass, non-admin realm use, unknown-user disclosure, password
lockout, expired or exhausted MFA, challenge replay, session-token hashing, recovery replay,
username normalization, forced non-admin session realms, and duplicate recovery hashes.

Deployment must inject the MFA encryption cipher/key and environment-approved limit values. Raw
passwords, TOTP secrets, MFA codes, recovery codes, session tokens, and CSRF tokens must never be
logged or stored. Operational key rotation and break-glass ownership require deployment approval;
they are not embedded in source defaults.
