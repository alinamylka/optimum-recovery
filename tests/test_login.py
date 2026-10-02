from fastapi.testclient import TestClient


def client(tmp_path, monkeypatch):
    from app import auth, db, mailer
    from app.main import app

    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "recovery.db"))
    monkeypatch.setattr(mailer, "start", lambda: None)
    monkeypatch.setenv("USERS", "alina:s3cret")
    monkeypatch.setenv("ADMINS", "alina")
    auth._key.cache_clear()
    return TestClient(app)


def test_sign_in_page_instead_of_browser_prompt(tmp_path, monkeypatch):
    with client(tmp_path, monkeypatch) as c:
        r = c.get("/account", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login?next=/account"
        assert "www-authenticate" not in r.headers

        r = c.post("/login", data={"username": "alina", "password": "wrong", "next": "/account"})
        assert r.status_code == 401 and "Wrong login or password" in r.text

        r = c.post("/login", data={"username": "alina", "password": "s3cret", "next": "/account"}, follow_redirects=False)
        assert r.headers["location"] == "/account"
        assert c.get("/account").status_code == 200

        c.post("/logout")
        assert c.get("/account", follow_redirects=False).status_code == 303


def test_password_change_ends_sessions(tmp_path, monkeypatch):
    from app import auth, db

    with client(tmp_path, monkeypatch) as c:
        c.post("/login", data={"username": "alina", "password": "s3cret"})
        assert c.get("/account").status_code == 200
        db.update_login("alina", password_hash=auth.hash_password("new"))
        assert c.get("/account", follow_redirects=False).status_code == 303


def test_api_keeps_basic_auth(tmp_path, monkeypatch):
    with client(tmp_path, monkeypatch) as c:
        r = c.get("/api/athletes/1/analysis")
        assert r.status_code == 401 and r.headers["www-authenticate"] == "Basic"
        assert c.get("/api/athletes/1/analysis", auth=("alina", "s3cret")).status_code == 404


def test_next_stays_on_site(tmp_path, monkeypatch):
    with client(tmp_path, monkeypatch) as c:
        r = c.post("/login", data={"username": "alina", "password": "s3cret", "next": "//evil.example"}, follow_redirects=False)
        assert r.headers["location"] == "/"


def test_athlete_name_from_intervals(tmp_path, monkeypatch):
    from app import main

    monkeypatch.setattr(main, "fetch_intervals_name", lambda athlete_id, key: "levisek")
    monkeypatch.setattr(main, "_sync", lambda a: None)
    with client(tmp_path, monkeypatch) as c:
        c.post("/login", data={"username": "alina", "password": "s3cret"})
        r = c.post("/athletes", data={"intervals_id": "i50345", "api_key": "k"}, follow_redirects=False)
        assert r.status_code == 303
        assert "levisek" in c.get(r.headers["location"]).text
        assert c.post("/athletes", data={"name": " "}).status_code == 400
