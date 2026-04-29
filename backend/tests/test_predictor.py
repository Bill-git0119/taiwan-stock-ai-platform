import math

from ai_engine.predictor import predict


def _trend_up(n=80):
    return [100 + i * 0.6 + math.sin(i / 5) * 1.5 for i in range(n)]


def _trend_down(n=80):
    return [200 - i * 0.5 + math.sin(i / 5) * 1.5 for i in range(n)]


def _flat(n=80):
    return [150 + math.sin(i / 7) * 2 for i in range(n)]


def test_predict_handles_short_series():
    assert predict("X", []) is None
    assert predict("X", [1, 2, 3]) is None


def test_predict_uptrend_is_bullish():
    p = predict("UP", _trend_up())
    assert p is not None
    assert p.prob_up_5d > 0.5
    assert p.expected_return_10d > 0
    assert 0 <= p.confidence <= 1
    assert p.return_low_10d <= p.expected_return_10d <= p.return_high_10d


def test_predict_downtrend_is_bearish():
    p = predict("DN", _trend_down())
    assert p is not None
    assert p.prob_up_5d < 0.5
    assert p.expected_return_10d < 0


def test_predict_flat_is_neutral_ish():
    p = predict("FLAT", _flat())
    assert p is not None
    assert 0.3 < p.prob_up_5d < 0.7
    assert 0 <= p.win_rate <= 1


def test_predict_to_dict_serializable():
    p = predict("UP", _trend_up())
    d = p.to_dict()
    assert d["symbol"] == "UP"
    assert "prob_up_5d" in d and "expected_return_10d" in d
    assert "confidence" in d
