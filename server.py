from fastapi import FastAPI
import json
import os
import uuid

app = FastAPI()

FILE = "users.json"


def load_users():
    if not os.path.exists(FILE):
        return []
    with open(FILE, "r") as f:
        return json.load(f)


def save_users(users):
    with open(FILE, "w") as f:
        json.dump(users, f, indent=2)


@app.get("/users")
def get_users():
    return load_users()


@app.post("/users")
def create_user(name: str):
    users = load_users()

    user = {
        "id": str(uuid.uuid4()),
        "name": name,
        "enabled": True,
        "params": {}
    }

    users.append(user)
    save_users(users)

    return user


@app.delete("/users/{user_id}")
def delete_user(user_id: str):
    users = load_users()

    users = [u for u in users if u["id"] != user_id]

    save_users(users)

    return {"status": "deleted"}