from __future__ import annotations

import getpass
import secrets
from pathlib import Path
from urllib.parse import quote_plus

import pymysql


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    host = input("MySQL host [127.0.0.1]: ").strip() or "127.0.0.1"
    port = int(input("MySQL port [3306]: ").strip() or "3306")
    root_user = input("MySQL administrator [root]: ").strip() or "root"
    root_password = getpass.getpass("MySQL administrator password: ")
    database = "ai_knowledge_base"
    app_user = "ai_kb_user"
    app_password = secrets.token_urlsafe(24)

    connection = pymysql.connect(host=host, port=port, user=root_user, password=root_password, charset="utf8mb4", autocommit=True)
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
            for allowed_host in ("localhost", "127.0.0.1"):
                cursor.execute(f"CREATE USER IF NOT EXISTS '{app_user}'@'{allowed_host}' IDENTIFIED BY %s", (app_password,))
                cursor.execute(f"ALTER USER '{app_user}'@'{allowed_host}' IDENTIFIED BY %s", (app_password,))
                cursor.execute(f"GRANT ALL PRIVILEGES ON `{database}`.* TO '{app_user}'@'{allowed_host}'")
            cursor.execute("FLUSH PRIVILEGES")
    finally:
        connection.close()

    database_url = f"mysql+pymysql://{quote_plus(app_user)}:{quote_plus(app_password)}@127.0.0.1:{port}/{database}?charset=utf8mb4"
    env_file = ROOT / ".env"
    existing = [line for line in env_file.read_text(encoding="utf-8").splitlines() if not line.startswith("DATABASE_URL=")] if env_file.exists() else []
    existing.append(f"DATABASE_URL={database_url}")
    env_file.write_text("\n".join(existing) + "\n", encoding="utf-8")
    print("Database and application user created. DATABASE_URL was written to .env.")


if __name__ == "__main__":
    main()
