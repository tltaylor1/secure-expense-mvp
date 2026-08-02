import os

from dotenv import load_dotenv

load_dotenv()

# Fail fast at import time: a missing secret must stop the app, because the
# tempting alternative (a hardcoded default) becomes the production secret
# the day someone forgets to set the real one.
SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY is not set. Copy .env.example to .env first.")

TOKEN_TTL_MINUTES = int(os.environ.get("TOKEN_TTL_MINUTES", "60"))

# A database URL is a connection target, not a secret, so unlike SECRET_KEY it
# may default: SQLite for a zero-setup local run and for tests. Docker Compose
# overrides this with the PostgreSQL URL, credentials included, from the
# environment. The password never appears in code or in compose itself.
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./expenses.db")

# Receipt storage: server-side directory, gitignored, files under
# server-generated names only. The cap bounds what one upload can cost.
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "./uploads")
MAX_RECEIPT_BYTES = 5_000_000

# Demo account password, used only by the seed script. It lives in .env like
# every other credential; even demo passwords are never written in the
# repository. The seed script fails without it, the same rule as SECRET_KEY.
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD")
