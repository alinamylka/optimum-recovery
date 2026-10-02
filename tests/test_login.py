from fastapi.testclient import TestClient


def client(tmp_path, monkeypatch):
    from app import auth, db, mailer
    from app.main import app

    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "recovery.db"))
    monkeypatch.setattr(mailer, "start", lambda: None)
    monkeypatch.setenv("USERS", "alina:s3cret")
    monkeypatch.setenv("ADMINS", "alina")
    auth._key.cache_clear()
    return TestClient(app, headers={"Accept-Language": "en"})


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


def _sign_in(c, username="alina", password="s3cret"):
    c.post("/login", data={"username": username, "password": password})


def _link(html):
    import re

    return re.search(r'value="https?://[^"]*?(/reset\?token=[^"]+)"', html).group(1).replace("&amp;", "&")


def test_coach_invites_athlete_with_signup_link(tmp_path, monkeypatch):
    from app import db, mailer

    sent = []
    monkeypatch.setattr(mailer, "configured", lambda: True)
    monkeypatch.setattr(mailer, "send", lambda to, subject, html, text: sent.append((to, text)))
    test_client = client(tmp_path, monkeypatch)
    monkeypatch.setenv("USERS", "alina:s3cret,arek:c0achpass")
    with test_client as c:
        athlete = db.add_athlete("arek", "levisek", None, None)
        _sign_in(c, "arek", "c0achpass")
        r = c.post(f"/athletes/{athlete}/account", data={"new_username": "Levi", "email": "levi@example.com"})
        assert "levi@example.com" in r.text and sent[0][0] == "levi@example.com"
        link = _link(r.text)
        assert link in sent[0][1]

        c.cookies.clear()
        assert "Your login: <b>levi</b>" in c.get(link).text
        r = c.post("/reset", data={"token": link.split("=", 1)[1], "password": "athlete-pw", "again": "athlete-pw"}, follow_redirects=False)
        assert r.status_code == 303
        assert c.get("/account").status_code == 200
        # The link works once: the password it was made for is gone.
        assert c.get(link).status_code == 400
        assert db.login("levi")["email"] == "levi@example.com"


def test_forgot_password_by_email_and_sign_in_with_email(tmp_path, monkeypatch):
    from app import db, mailer

    sent = []
    monkeypatch.setattr(mailer, "configured", lambda: True)
    monkeypatch.setattr(mailer, "send", lambda to, subject, html, text: sent.append(text))
    with client(tmp_path, monkeypatch) as c:
        db.set_mail("alina", "alina@example.com", True)
        assert "on its way" in c.post("/forgot", data={"who": "nobody@example.com"}).text and not sent
        c.post("/forgot", data={"who": "Alina@example.com"})
        token = sent[0].split("token=")[1].split()[0]
        assert c.post("/reset", data={"token": token, "password": "short", "again": "short"}).status_code == 400
        c.post("/reset", data={"token": token, "password": "brand-new-pw", "again": "brand-new-pw"})
        c.cookies.clear()
        r = c.post("/login", data={"username": "alina@example.com", "password": "brand-new-pw"}, follow_redirects=False)
        assert r.status_code == 303


def test_rename_follows_everywhere_and_keeps_session(tmp_path, monkeypatch):
    from app import db

    with client(tmp_path, monkeypatch) as c:
        athlete = db.add_athlete("alina", "Alina", None, None)
        db.link_login(athlete, "alina")
        _sign_in(c)
        c.post("/account/username", data={"username": "Ala"})
        assert c.get("/account", follow_redirects=False).status_code == 200
        assert db.login("alina") is None and db.athlete_by_id(athlete)["owner"] == "ala"
        assert db.own_profile("ala")["id"] == athlete


def test_change_password_needs_current(tmp_path, monkeypatch):
    with client(tmp_path, monkeypatch) as c:
        _sign_in(c)
        r = c.post("/account/password", data={"current": "nope", "password": "longenough", "again": "longenough"})
        assert "Obecne hasło jest złe" in r.text
        c.post("/account/password", data={"current": "s3cret", "password": "longenough", "again": "longenough"})
        assert c.get("/account", follow_redirects=False).status_code == 200
        c.cookies.clear()
        assert c.post("/login", data={"username": "alina", "password": "longenough"}, follow_redirects=False).status_code == 303


def test_pages_speak_the_login_language(tmp_path, monkeypatch):
    from app import db

    with client(tmp_path, monkeypatch) as c:
        c.headers["Accept-Language"] = "pl-PL,pl"
        assert "Zaloguj się" in c.get("/login").text
        _sign_in(c)
        db.set_language("alina", "en")
        assert "Monday email" in c.get("/account").text
        db.set_language("alina", "pl")
        page = c.get("/account").text
        assert "Poniedziałkowy mail" in page and "Wyloguj" in page
