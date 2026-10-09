from src.mlops.tracking import _param_value, log_runs


def test_param_value_serializes_reproducibility_inputs():
    assert _param_value([2023, 2024]) == "[2023, 2024]"
    assert _param_value({"split": "validation"}) == '{"split": "validation"}'


def test_tracking_can_be_disabled_without_mlflow(monkeypatch, capsys):
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "")
    log_runs("test", [], {})
    assert "기록을 건너뜁니다" in capsys.readouterr().out
