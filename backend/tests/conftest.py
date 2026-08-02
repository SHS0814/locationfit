import os

# Unit tests use dependency-level security tests and do not require a live usage-ledger database.
os.environ.setdefault("AI_SECURITY_ENABLED", "false")
