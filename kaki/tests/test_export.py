"""kaki_model.json must reproduce the served model exactly."""
import json
import pickle

import numpy as np

import kaki_ml


def _load(trained):
    with open(trained / "kaki_model.json", encoding="utf-8") as f:
        model_json = json.load(f)
    with open(trained / "models" / "scam_model.pkl", "rb") as f:
        pipe = pickle.load(f)["pipeline"]
    return model_json, pipe


def browser_score(model_json, text):
    w = model_json["weights"]
    z = model_json["intercept"] + sum(w.get(f, 0.0) for f in kaki_ml.features(text))
    return kaki_ml.sigmoid(z)


def test_schema(trained):
    m, _ = _load(trained)
    assert m["schema_version"] == kaki_ml.SCHEMA_VERSION
    assert m["meta"]["thresholds"] == kaki_ml.THRESHOLDS
    assert m["rules"]["scam_phrases"] == kaki_ml.SCAM_PHRASES
    assert m["meta"]["data_sources"]["sms"] == "fallback"   # offline run is tagged


def test_weights_are_signed(trained):
    m, _ = _load(trained)
    vals = np.array(list(m["weights"].values()))
    assert (vals > 0).any() and (vals < 0).any()


def test_browser_score_equals_server_score(trained, sg_texts):
    m, pipe = _load(trained)
    for text in sg_texts + ["", "hello", "安全账户 transfer now"]:
        server = float(pipe.predict_proba([text])[0, 1])
        assert abs(browser_score(m, text) - server) < 1e-3, text


def test_committed_model_json_matches_schema():
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "kaki_model.json"), encoding="utf-8") as f:
        m = json.load(f)
    assert m["schema_version"] == kaki_ml.SCHEMA_VERSION
    assert m["meta"]["thresholds"] == kaki_ml.THRESHOLDS
    assert m["rules"]["scam_phrases"] == kaki_ml.SCAM_PHRASES
    assert m["weights"] and isinstance(m["intercept"], float)


def test_manifest_lists_both_models(trained):
    with open(trained / "models" / "manifest.json") as f:
        manifest = json.load(f)
    assert set(manifest["files"]) == {"scam_model.pkl", "txn_model.pkl"}
