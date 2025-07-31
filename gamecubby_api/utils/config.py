from pathlib import Path
import os
import secrets
import re
from dotenv import load_dotenv

ENV_PATH = Path(__file__).parent.parent / ".env"

#print("[debug] Writing to:", ENV_PATH.resolve())

load_dotenv(dotenv_path=ENV_PATH)

SECRET_KEY = os.getenv("SECRET_KEY")

if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)
    existing = ENV_PATH.read_text() if ENV_PATH.exists() else ""

    if re.search(r"^\s*SECRET_KEY\s*=", existing, re.MULTILINE):
        new_contents = re.sub(
            r"^\s*SECRET_KEY\s*=.*$",
            f"SECRET_KEY={SECRET_KEY}",
            existing,
            flags=re.MULTILINE
        )
        ENV_PATH.write_text(new_contents)
        print("[config] SECRET_KEY was empty — updated with generated key")
    else:
        with ENV_PATH.open("a") as f:
            if not existing.endswith("\n"):
                f.write("\n")
            f.write(f"SECRET_KEY={SECRET_KEY}\n")
        print("[config] SECRET_KEY was missing — new key generated and added to .env")

ALGORITHM = "HS256"
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
QUERY_LIMIT = int(os.getenv("QUERY_LIMIT", "50"))
