"""
train.py — Kaki training script (the ONLY training pipeline; the backend API and
the browser demo both serve what this script produces).
Event code: SSF2026. Intended to run on IBM LinuxONE Community Cloud (s390x);
the architecture it actually ran on is recorded in kaki_model.json.

Datasets:
  1. UCI SMS Spam Collection   kagglehub: uciml/sms-spam-collection-dataset
  2. PaySim synthetic payments kagglehub: ealaxi/paysim1
  3. scam_sg.csv               Singapore-style scam/legit messages (this repo)

If a Kaggle download fails, a small embedded fallback is used and every
metric is tagged data_source="fallback" — those numbers are NOT reportable.

Outputs (in --out-dir, default: this folder):
  kaki_model.json       browser weights + thresholds + rules + honest metrics
  models/scam_model.pkl served by backend/app.py
  models/txn_model.pkl  served by backend/app.py
  models/manifest.json  SHA-256 of each pickle, checked before loading

Run:
  pip install -r requirements-train.txt
  python train.py               # add --no-plots on headless machines
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import pickle
import platform
import sys

import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict, train_test_split
from sklearn.pipeline import Pipeline

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kaki_ml  # noqa: E402

LOW_CONFIDENCE_N = 30   # per-group metrics on fewer rows are flagged


# ─────────────────────────────────────────────────────────────────────────────
# 1. LOAD DATASETS
# ─────────────────────────────────────────────────────────────────────────────

def load_sms_spam(offline=False):
    """UCI SMS Spam Collection → (df[text,label,lang,source], data_source)."""
    if not offline:
        try:
            import kagglehub
            p = kagglehub.dataset_download("uciml/sms-spam-collection-dataset")
            for fname in ["spam.csv", "SMSSpamCollection"]:
                fp = os.path.join(p, fname)
                if os.path.exists(fp):
                    if fname.endswith(".csv"):
                        df = pd.read_csv(fp, encoding="latin-1")[["v1", "v2"]]
                        df.columns = ["label_str", "text"]
                    else:
                        df = pd.read_csv(fp, sep="\t", header=None, names=["label_str", "text"])
                    df["label"] = (df["label_str"].str.lower() == "spam").astype(int)
                    df["lang"], df["source"] = "en", "uci"
                    print(f"UCI SMS Spam: {len(df)} rows, {df.label.sum()} spam")
                    return df[["text", "label", "lang", "source"]], "kaggle:uciml/sms-spam-collection-dataset"
        except Exception as e:  # network, auth, missing package
            print(f"!! kagglehub UCI failed: {e}")
    print("!! Using embedded UCI fallback — metrics will be tagged 'fallback' and are NOT reportable.")
    rows = [
        ("Free prize! Call now to claim your reward. Limited time offer!", 1),
        ("URGENT: Your account has been suspended. Click link to verify.", 1),
        ("WINNER!! You have been selected for a cash prize, reply YES now", 1),
        ("Your mobile number has won 5000 pounds, call to claim", 1),
        ("Hey, are we still on for lunch tomorrow?", 0),
        ("Your parcel will arrive between 2-4pm today.", 0),
        ("Can you pick up some bread on the way home", 0),
        ("Meeting moved to 3pm, see you there", 0),
    ]
    df = pd.DataFrame(rows, columns=["text", "label"])
    df["lang"], df["source"] = "en", "uci"
    return df, "fallback"


def load_scam_sg():
    p = os.path.join(HERE, "scam_sg.csv")
    df = pd.read_csv(p)
    df["source"] = "sg"
    print(f"SG scripts: {len(df)} rows, {df.label.sum()} scam, langs: {sorted(df.lang.unique())}")
    return df[["text", "label", "lang", "source"]]


PAYSIM_COLS = ["step", "type", "amount", "oldbalanceOrg", "newbalanceOrig", "isFraud"]


def load_paysim(offline=False, legit_sample=400_000, seed=42):
    """PaySim, read in chunks over the WHOLE file: every fraud row is kept and
    legitimate rows are uniformly sampled (the file is time-ordered, so taking
    the first N rows would cover only the first few simulated days)."""
    if not offline:
        try:
            import kagglehub
            p = kagglehub.dataset_download("ealaxi/paysim1")
            fps = [os.path.join(p, f) for f in os.listdir(p) if f.endswith(".csv")]
            if fps:
                rng = np.random.default_rng(seed)
                total = 6_362_620                      # PaySim row count
                keep_p = min(1.0, legit_sample / total)
                parts = []
                for chunk in pd.read_csv(fps[0], usecols=PAYSIM_COLS, chunksize=500_000):
                    mask = (chunk.isFraud == 1) | (rng.random(len(chunk)) < keep_p)
                    parts.append(chunk[mask])
                df = pd.concat(parts, ignore_index=True)
                print(f"PaySim: {len(df)} rows sampled, {df.isFraud.sum()} fraud")
                return df, "kaggle:ealaxi/paysim1"
        except Exception as e:
            print(f"!! kagglehub PaySim failed: {e}")
    print("!! Using synthetic PaySim fallback — metrics tagged 'fallback', NOT reportable.")
    rng = np.random.default_rng(seed)

    def mk(n, fraud):
        bal = rng.uniform(500, 80000, n)
        amt = rng.uniform(bal * 0.5, bal * 0.99) if fraud else rng.uniform(5, np.maximum(bal * 0.9, 10))
        return pd.DataFrame({
            "step": rng.integers(1, 744, n),
            "type": rng.choice(["TRANSFER", "CASH_OUT"] if fraud else list(kaki_ml.TYPE_MAP), n),
            "amount": amt.round(2),
            "oldbalanceOrg": bal.round(2),
            "newbalanceOrig": np.maximum(0, bal - amt).round(2),
            "isFraud": int(fraud),
        })
    df = pd.concat([mk(4850, False), mk(150, True)]).sample(frac=1, random_state=seed)
    return df.reset_index(drop=True), "fallback"


# ─────────────────────────────────────────────────────────────────────────────
# 2. SCAM MESSAGE CLASSIFIER (Model A)
# ─────────────────────────────────────────────────────────────────────────────

def make_scam_pipeline():
    # Binary features + LR: logit == intercept + sum(weights present), which
    # is what kaki-demo.html computes from kaki_model.json.
    return Pipeline([
        ("vec", CountVectorizer(analyzer=kaki_ml.analyzer, binary=True, lowercase=False)),
        ("clf", LogisticRegression(C=1.0, class_weight="balanced", max_iter=5000, random_state=42)),
    ])


def prepare_messages(df):
    df = df.dropna(subset=["text"]).copy()
    df["norm"] = df["text"].map(kaki_ml.normalise)
    df = df[df["norm"] != ""]
    # Exact duplicates (after normalisation) would sit in train and test at once.
    conflicting = df.groupby("norm")["label"].nunique()
    df = df[~df["norm"].isin(conflicting[conflicting > 1].index)]
    before = len(df)
    df = df.drop_duplicates(subset="norm").reset_index(drop=True)
    print(f"Removed {before - len(df)} duplicate messages; {len(df)} remain")
    return df


def _strata(df):
    s = df["label"].astype(str) + "_" + df["source"] + "_" + df["lang"]
    counts = s.value_counts()
    # Strata too small to split fall back to label+source, then label.
    s = s.where(s.map(counts) >= 2, df["label"].astype(str) + "_" + df["source"])
    counts = s.value_counts()
    return s.where(s.map(counts) >= 2, df["label"].astype(str))


def threshold_metrics(y, p, hits=None):
    """Model-only metrics at the thresholds; with `hits`, also the metrics of
    the full decision (model + rule phrases) that users actually see."""
    y, p = np.asarray(y), np.asarray(p)
    n_pos, n_neg = int(y.sum()), int((1 - y).sum())
    flagged = p >= kaki_ml.THRESHOLDS["suspicious"]
    blocked = p >= kaki_ml.THRESHOLDS["scam"]
    tp = int((blocked & (y == 1)).sum())
    m = {
        "n": int(len(y)), "n_scam": n_pos, "n_legit": n_neg,
        # catch_rate: scams that get at least an amber warning
        "catch_rate": round(float(flagged[y == 1].mean()), 4) if n_pos else None,
        # false_alarm_rate: legit messages that get at least an amber warning
        "false_alarm_rate": round(float(flagged[y == 0].mean()), 4) if n_neg else None,
        "precision_at_scam": round(tp / int(blocked.sum()), 4) if blocked.sum() else None,
        "recall_at_scam": round(tp / n_pos, 4) if n_pos else None,
        "roc_auc": round(float(roc_auc_score(y, p)), 4) if n_pos and n_neg else None,
        "low_confidence": bool(len(y) < LOW_CONFIDENCE_N),
    }
    if hits is not None:
        decided = np.array([kaki_ml.decide(pi, h) for pi, h in zip(p, hits)])
        warned = decided != "safe"
        m["with_rules"] = {
            "catch_rate": round(float(warned[y == 1].mean()), 4) if n_pos else None,
            "false_alarm_rate": round(float(warned[y == 0].mean()), 4) if n_neg else None,
        }
    return m


def train_scam_model(df, n_splits=5):
    """Out-of-fold evaluation on every row, then a final fit on all rows."""
    df = prepare_messages(df)
    strata = _strata(df)
    k = int(max(2, min(n_splits, strata.value_counts().min())))
    cv = StratifiedKFold(n_splits=k, shuffle=True, random_state=42)
    oof = cross_val_predict(make_scam_pipeline(), df["text"].values, df["label"].values,
                            cv=list(cv.split(df, strata)), method="predict_proba")[:, 1]
    df["oof"] = oof
    df["hits"] = df["text"].map(kaki_ml.rule_hits)

    metrics = {
        "protocol": f"{k}-fold stratified out-of-fold predictions; thresholds {kaki_ml.THRESHOLDS}",
        "overall": threshold_metrics(df.label, df.oof, df.hits),
        "per_source": {s: threshold_metrics(g.label, g.oof, g.hits) for s, g in df.groupby("source")},
        "per_language_sg": {l: threshold_metrics(g.label, g.oof, g.hits)
                            for l, g in df[df.source == "sg"].groupby("lang")},
    }
    pipe = make_scam_pipeline().fit(df["text"].values, df["label"].values)
    return pipe, metrics, df


def print_scam_metrics(metrics):
    def line(name, m):
        flag = "  (low confidence)" if m["low_confidence"] else ""
        r = m["with_rules"]
        print(f"  {name:12s} n={m['n']:5d}  AUC={m['roc_auc']}  catch={m['catch_rate']}  "
              f"false_alarm={m['false_alarm_rate']}  | +rules catch={r['catch_rate']} "
              f"false_alarm={r['false_alarm_rate']}{flag}")
    print(metrics["protocol"])
    line("overall", metrics["overall"])
    for s, m in metrics["per_source"].items():
        line(f"source:{s}", m)
    for l, m in metrics["per_language_sg"].items():
        line(f"sg:{l}", m)


# ─────────────────────────────────────────────────────────────────────────────
# 3. TRANSACTION RISK MODEL (Model B)
# ─────────────────────────────────────────────────────────────────────────────

def featurise_paysim(df):
    return np.array([
        kaki_ml.txn_features(a, o, n, t, s % 24)
        for a, o, n, t, s in zip(df.amount, df.oldbalanceOrg, df.newbalanceOrig, df.type, df.step)
    ], dtype=float)


def train_txn_model(raw):
    X = featurise_paysim(raw)
    y = raw["isFraud"].values.astype(int)
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    rf = RandomForestClassifier(n_estimators=200, max_depth=12, class_weight="balanced",
                                random_state=42, n_jobs=-1).fit(X_tr, y_tr)
    p = rf.predict_proba(X_te)[:, 1]
    pred = p >= 0.5
    tp = int((pred & (y_te == 1)).sum())
    metrics = {
        "protocol": "80/20 stratified holdout on the sampled PaySim rows",
        "n_test": int(len(y_te)), "fraud_rate": round(float(y.mean()), 5),
        "roc_auc": round(float(roc_auc_score(y_te, p)), 4),
        "pr_auc": round(float(average_precision_score(y_te, p)), 4),
        "precision_at_0_5": round(tp / max(1, int(pred.sum())), 4),
        "recall_at_0_5": round(tp / max(1, int(y_te.sum())), 4),
        "feature_importances": {f: round(float(v), 4)
                                for f, v in zip(kaki_ml.TXN_FEATURES, rf.feature_importances_)},
        "caveat": ("PaySim balances are known to leak the label (fraud empties the account), "
                   "amounts are simulated units not SGD, and fraud only occurs in TRANSFER/CASH_OUT."),
    }
    rf.fit(X, y)   # final model on all sampled rows
    return rf, metrics


# ─────────────────────────────────────────────────────────────────────────────
# 4. EXPORT
# ─────────────────────────────────────────────────────────────────────────────

def browser_export(pipe, scam_metrics, txn_metrics, data_sources):
    vec, clf = pipe.named_steps["vec"], pipe.named_steps["clf"]
    coef = clf.coef_[0]
    # Every weight is exported (signed), so the browser score is exact.
    weights = {f: round(float(coef[i]), 5) for f, i in sorted(vec.vocabulary_.items())
               if abs(coef[i]) >= 1e-5}
    return {
        "schema_version": kaki_ml.SCHEMA_VERSION,
        "meta": {
            "description": "Kaki scam classifier: binary word/Han-char n-gram logistic regression. "
                           "score = sigmoid(intercept + sum(weights of features present)).",
            "trained_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "trained_on_arch": platform.machine(),
            "event_code": "SSF2026",
            "sklearn_version": sklearn.__version__,
            "data_sources": data_sources,
            "thresholds": kaki_ml.THRESHOLDS,
            "metrics": {"model_a": scam_metrics, "model_b": txn_metrics},
        },
        "intercept": round(float(clf.intercept_[0]), 5),
        "weights": weights,
        "rules": {"scam_phrases": kaki_ml.SCAM_PHRASES},
        "transfer_heuristic": kaki_ml.TRANSFER_HEURISTIC,
    }


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def save_artifacts(out_dir, pipe, rf, model_json):
    mdir = os.path.join(out_dir, "models")
    os.makedirs(mdir, exist_ok=True)
    files = {
        "scam_model.pkl": {"schema_version": kaki_ml.SCHEMA_VERSION, "pipeline": pipe},
        "txn_model.pkl": {"schema_version": kaki_ml.SCHEMA_VERSION, "model": rf,
                          "features": kaki_ml.TXN_FEATURES},
    }
    manifest = {"schema_version": kaki_ml.SCHEMA_VERSION, "sklearn_version": sklearn.__version__,
                "trained_at": model_json["meta"]["trained_at"],
                "data_sources": model_json["meta"]["data_sources"], "files": {}}
    for name, obj in files.items():
        path = os.path.join(mdir, name)
        with open(path, "wb") as f:
            pickle.dump(obj, f)
        manifest["files"][name] = _sha256(path)
        print(f"Saved: {path}")
    with open(os.path.join(mdir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    out = os.path.join(out_dir, "kaki_model.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(model_json, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Exported: {out} ({os.path.getsize(out) / 1024:.0f} KB, {len(model_json['weights'])} weights)")


def save_plots(scored_df, out_dir):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from sklearn.metrics import RocCurveDisplay, precision_recall_curve
    except ImportError:
        print("matplotlib not installed — skipping plots")
        return
    y, p = scored_df.label.values, scored_df.oof.values
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    RocCurveDisplay.from_predictions(y, p, ax=axes[0], name="Model A (out-of-fold)")
    axes[0].plot([0, 1], [0, 1], "k--", alpha=.4)
    prec, rec, thr = precision_recall_curve(y, p)
    axes[1].plot(thr, prec[:-1], label="Precision")
    axes[1].plot(thr, rec[:-1], label="Recall")
    axes[1].axvline(kaki_ml.THRESHOLDS["scam"], color="#ef4444", ls="--", label="Scam threshold")
    axes[1].axvline(kaki_ml.THRESHOLDS["suspicious"], color="#f59e0b", ls="--", label="Suspicious threshold")
    axes[1].legend(fontsize=8)
    plt.tight_layout()
    path = os.path.join(out_dir, "model_a_results.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {path}")


# ─────────────────────────────────────────────────────────────────────────────
# 5. MAIN
# ─────────────────────────────────────────────────────────────────────────────
# Voice datasets for future ASR fine-tuning (not used by this script):
# common_voice (en/zh-CN/ms/ta), google/fleurs, AISHELL-1/3, IISc-MILE Tamil ASR.

def main(argv=None):
    ap = argparse.ArgumentParser(description="Train Kaki models")
    ap.add_argument("--out-dir", default=HERE)
    ap.add_argument("--offline", action="store_true", help="skip Kaggle; use embedded fallbacks")
    ap.add_argument("--no-plots", action="store_true")
    ap.add_argument("--paysim-sample", type=int, default=400_000, help="legit PaySim rows to sample")
    args = ap.parse_args(argv)

    print(f"Kaki training — {platform.machine()} / Python {platform.python_version()}")

    uci, uci_src = load_sms_spam(args.offline)
    msgs = pd.concat([uci, load_scam_sg()], ignore_index=True)
    print("\nMODEL A: scam message classifier")
    pipe, scam_metrics, scored = train_scam_model(msgs)
    scam_metrics["data_source"] = uci_src
    print_scam_metrics(scam_metrics)

    print("\nMODEL B: transaction risk (PaySim random forest)")
    raw, paysim_src = load_paysim(args.offline, args.paysim_sample)
    rf, txn_metrics = train_txn_model(raw)
    txn_metrics["data_source"] = paysim_src
    print(f"  ROC-AUC={txn_metrics['roc_auc']}  PR-AUC={txn_metrics['pr_auc']}")

    sources = {"sms": uci_src, "sg": "scam_sg.csv", "paysim": paysim_src}
    model_json = browser_export(pipe, scam_metrics, txn_metrics, sources)
    save_artifacts(args.out_dir, pipe, rf, model_json)
    if not args.no_plots:
        save_plots(scored, args.out_dir)
    if "fallback" in (uci_src, paysim_src):
        print("\n!! WARNING: trained on fallback data. Do not report these metrics.")


if __name__ == "__main__":
    main()
