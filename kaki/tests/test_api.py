import json
import shutil

import pytest

import app as kaki_app


@pytest.fixture()
def client(trained, monkeypatch):
    monkeypatch.setenv("KAKI_RATE_LIMIT", "1000")
    return kaki_app.create_app(model_dir=str(trained / "models")).test_client()


def test_health(client):
    assert client.get("/api/health").get_json()["status"] == "ok"


@pytest.mark.parametrize("path", ["/score", "/api/scan-message"])
def test_score_contract(client, path):
    r = client.post(path, json={"text": "Transfer all funds to our safe account now", "lang": "zh"})
    j = r.get_json()
    assert r.status_code == 200
    assert {"score", "label", "matchedWords", "message", "lang"} <= set(j)
    assert j["label"] in ("suspicious", "scam") and "safe account" in j["matchedWords"]
    assert j["lang"] == "zh"
    assert "text_snippet" not in j


@pytest.mark.parametrize("lang", ["en", "zh", "ms", "ta", "mandarin", "xx"])
def test_all_languages_have_warnings(client, lang):
    j = client.post("/score", json={"text": "hello", "lang": lang}).get_json()
    assert j["lang"] == kaki_app.resolve_lang(lang) and j["message"]


@pytest.mark.parametrize("body", [[1, 2], "text", {"text": 5}, {"text": ""}, {"text": "x" * 2001}])
def test_bad_message_input(client, body):
    r = client.post("/score", data=json.dumps(body), content_type="application/json")
    assert r.status_code == 400


def test_malformed_json(client):
    assert client.post("/score", data="{nope", content_type="application/json").status_code == 400


@pytest.mark.parametrize("body", [
    {"amount": "abc", "balance_before": 100},
    {"amount": -5, "balance_before": 100},
    {"amount": float("nan"), "balance_before": 100},
    {"amount": 5, "balance_before": 100, "recipient_known": "no"},
    {"amount": 5, "balance_before": 100, "type": "HACK"},
    {"amount": 5},
])
def test_bad_transfer_input(client, body):
    r = client.post("/api/scan-transfer", data=json.dumps(body), content_type="application/json")
    assert r.status_code == 400


def test_transfer_uses_message_context(client):
    base = {"amount": 900, "balance_before": 10000, "recipient_known": True}
    plain = client.post("/api/scan-transfer", json=base).get_json()
    ctx = client.post("/api/scan-transfer", json={**base, "message_context":
        "Money laundering case. Transfer all funds to safe account, do not tell anyone"}).get_json()
    assert ctx["message_label"] == "scam"
    assert ctx["fraud_probability"] >= min(1.0, plain["fraud_probability"] + 0.29)


def test_unknown_recipient_drain_is_scam(client):
    j = client.post("/api/scan-transfer", json={"amount": 9500, "balance_before": 10000,
                                                 "recipient_known": False}).get_json()
    assert j["label"] == "scam"


def test_tampered_model_refused(trained, tmp_path):
    d = tmp_path / "models"
    shutil.copytree(trained / "models", d)
    with open(d / "txn_model.pkl", "ab") as f:
        f.write(b"x")
    with pytest.raises(kaki_app.ModelError):
        kaki_app.create_app(model_dir=str(d))


def test_rate_limit(trained, monkeypatch):
    monkeypatch.setenv("KAKI_RATE_LIMIT", "2")
    c = kaki_app.create_app(model_dir=str(trained / "models")).test_client()
    codes = [c.post("/score", json={"text": "hi"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_cors_restricted(client):
    r = client.post("/score", json={"text": "hi"}, headers={"Origin": "https://evil.example"})
    assert "Access-Control-Allow-Origin" not in r.headers
    r = client.post("/score", json={"text": "hi"}, headers={"Origin": "http://localhost:8080"})
    assert r.headers.get("Access-Control-Allow-Origin") == "http://localhost:8080"
