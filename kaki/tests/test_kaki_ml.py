import kaki_ml


def test_normalise_masks_and_keeps_tamil_marks():
    assert kaki_ml.normalise("Pay S$1,000 at https://x.y/z or call 9123 4567!") == \
        "pay moneyfigure at url or call phonenumber"
    # Tamil vowel signs are combining marks and must survive
    assert kaki_ml.normalise("பாதுகாப்பான கணக்கு") == "பாதுகாப்பான கணக்கு"


def test_features_han_and_bigrams():
    f = kaki_ml.features("转账到安全账户 safe account")
    assert "安全" in f and "账户" in f and "safe account" in f


def test_rules_are_word_bounded():
    assert kaki_ml.rule_hits("Merry Christmas and a safe trip") == []
    assert "safe account" in kaki_ml.rule_hits("Move it to a SAFE ACCOUNT now")
    assert kaki_ml.rule_hits("请转到安全账户") == ["安全账户"]
    assert kaki_ml.rule_hits("A police reminder: stay safe") == []


def test_decide():
    t = kaki_ml.THRESHOLDS
    assert kaki_ml.decide(t["scam"], []) == "scam"
    assert kaki_ml.decide(t["suspicious"], ["x"]) == "scam"
    assert kaki_ml.decide(0.0, ["x"]) == "suspicious"
    assert kaki_ml.decide(0.0, ["x", "y"]) == "scam"
    assert kaki_ml.decide(0.0, []) == "safe"


def test_transfer_heuristic():
    assert kaki_ml.transfer_heuristic(9500, 10000, recipient_known=False) == 0.90
    assert kaki_ml.transfer_heuristic(50, 10000, recipient_known=True) == 0.0
