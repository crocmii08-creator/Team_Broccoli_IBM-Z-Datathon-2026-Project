"""The JS port inside kaki-demo.html must match kaki_ml.py exactly."""
import json
import os
import shutil
import subprocess

import pytest

import kaki_ml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EXTRA = [
    "Merry Christmas! Transfer S$5,000.50 to 123-456789-0 now",
    "Visit www.scam.xyz/abc?x=1 or http://a.b. Call +65 9123 4567",
    "500 SGD  sgd 20 $3 ２３ İstanbul",
    "你好　world  tab\there\nnewline",
    "",
    "!!!",
]

DRIVER = """
const fs = require('fs');
const {texts, phrases, th} = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const out = texts.map(t => {
  const hits = kakiRuleHits(t, phrases);
  return {norm: kakiNormalise(t), feats: kakiFeatures(t), hits,
          decisions: [0, 0.35, 0.5, 0.7].map(p => kakiDecide(p, hits, th))};
});
process.stdout.write(JSON.stringify(out));
"""


def _shared_js():
    with open(os.path.join(ROOT, "kaki-demo.html"), encoding="utf-8") as f:
        src = f.read()
    return src[src.index("// BEGIN kaki-shared"):src.index("// END kaki-shared")]


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_js_matches_python(tmp_path, sg_texts):
    texts = sg_texts + EXTRA
    (tmp_path / "p.js").write_text(_shared_js() + DRIVER, encoding="utf-8")
    (tmp_path / "in.json").write_text(json.dumps(
        {"texts": texts, "phrases": kaki_ml.SCAM_PHRASES, "th": kaki_ml.THRESHOLDS}), encoding="utf-8")
    res = subprocess.run(["node", str(tmp_path / "p.js"), str(tmp_path / "in.json")],
                         capture_output=True, check=True)
    js = json.loads(res.stdout.decode("utf-8"))
    for t, j in zip(texts, js):
        hits = kaki_ml.rule_hits(t)
        assert j["norm"] == kaki_ml.normalise(t), t
        assert set(j["feats"]) == set(kaki_ml.features(t)), t
        assert j["hits"] == hits, t
        assert j["decisions"] == [kaki_ml.decide(p, hits) for p in (0, 0.35, 0.5, 0.7)], t
