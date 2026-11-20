import json
import urllib.request
from app.storage.postgres.client import postgres_connection
from app.schemas.auth import UserOut
from app.storage.repositories.session_repository import delete_threads

BASE = "http://127.0.0.1:8765"
body = json.dumps({"username": "ui_flow_29166046", "password": "smoke-pass-1234"}).encode()
request = urllib.request.Request(BASE + "/api/app/auth/login", data=body, headers={"Content-Type": "application/json"}, method="POST")
login = json.loads(urllib.request.urlopen(request).read().decode())
user_payload = login["user"]
user = UserOut(**user_payload)
with postgres_connection() as connection, connection.cursor() as cursor:
    cursor.execute("SELECT id, user_id, thread_name, created_at FROM chat_threads WHERE id=75")
    row = cursor.fetchone()
print("thread", dict(row) if row else None)
if row and int(row["user_id"]) == int(user.id):
    deleted = delete_threads(user=user, thread_ids=[75])
    print("deleted", deleted)
else:
    print("skip")
