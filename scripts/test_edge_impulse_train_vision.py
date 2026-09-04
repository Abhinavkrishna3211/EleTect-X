"""Tests for edge_impulse_train_vision.py's select_model() override plumbing.

Covers the freeze-backbone / spatial-augmentation / color-space-augmentation
CLI flags added 4 Sep for the Boar-gap close-out session - the values they
validate against are a fixture, not a hardcoded tuple in this test file
either, mirroring the live customParameters shape confirmed via
GET /transfer-learning-models on project 1097972 that same day. No network
call is made - request() is monkeypatched.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import edge_impulse_train_vision as eitv


def _yolo_pro_model():
    """A trimmed but real-shaped YOLO-Pro transfer-learning-model entry.

    customParameters values/selectOptions match the live API response read
    4 Sep 2026 (project 1097972) - sizing/architecture-type plus the three
    advanced-section knobs this session added CLI overrides for.
    """
    return {
        "name": "YOLO-Pro",
        "learnBlockType": "keras-object-detection",
        "organizationModelId": 6493,
        "customParameters": [
            {"param": "epochs", "defaultValue": "100", "type": "int"},
            {"param": "learning-rate", "defaultValue": "0.001", "type": "float"},
            {
                "param": "sizing",
                "defaultValue": "small",
                "type": "select",
                "selectOptions": [
                    {"value": v}
                    for v in ("pico", "nano", "small", "medium", "large", "xlarge")
                ],
            },
            {"param": "use-pretrained-weights", "defaultValue": "true", "type": "flag"},
            {"param": "batch-size", "defaultValue": "16", "type": "int"},
            {"param": "freeze-backbone", "defaultValue": "false", "type": "flag"},
            {
                "param": "architecture-type",
                "defaultValue": "no_attn_relu",
                "type": "select",
                "selectOptions": [{"value": "attn_silu"}, {"value": "no_attn_relu"}],
            },
            {
                "param": "spatial-augmentation",
                "defaultValue": "low",
                "type": "select",
                "selectOptions": [
                    {"value": v} for v in ("none", "low", "medium", "high")
                ],
            },
            {
                "param": "color-space-augmentation",
                "defaultValue": "low",
                "type": "select",
                "selectOptions": [
                    {"value": v} for v in ("none", "low", "medium", "high")
                ],
            },
            {"param": "early-stopping-start-epoch", "defaultValue": "10", "type": "int"},
        ],
    }


@pytest.fixture(autouse=True)
def stub_request(monkeypatch):
    """select_model() only ever calls request() once, to list transfer-learning
    models - stub it to return the fixture above regardless of path/method,
    exactly as the live /{project}/transfer-learning-models response shapes it.
    """

    def fake_request(path, api_key, method="GET", body=None, timeout=180, retries=3):
        assert "/transfer-learning-models" in path
        fomo = {
            "type": "fomo_mobilenet_v2_a35",
            "learnBlockType": "keras-object-detection",
            "customParameters": [],
        }
        return {"transferLearningModels": [_yolo_pro_model(), fomo]}

    monkeypatch.setattr(eitv, "request", fake_request)


def test_no_overrides_keeps_model_defaults():
    """Omitting all three flags (the pre-4-Sep behaviour) leaves freeze-backbone/
    augmentation at whatever the model's own defaultValue is - untouched.
    """
    label, _visual, params = eitv.select_model(
        "proj", "key", "yolo-pro", yolo_variant="no_attn_relu", yolo_sizing="medium"
    )
    assert params["freeze-backbone"] == "false"
    assert params["spatial-augmentation"] == "low"
    assert params["color-space-augmentation"] == "low"
    assert label == "yolo-pro-medium-no_attn_relu"


def test_color_space_augmentation_override_applied():
    """--color-space-augmentation medium lands in customParameters and the label."""
    label, _visual, params = eitv.select_model(
        "proj",
        "key",
        "yolo-pro",
        yolo_variant="no_attn_relu",
        yolo_sizing="medium",
        color_space_augmentation="medium",
    )
    assert params["color-space-augmentation"] == "medium"
    # Untouched knobs stay at the model's own default.
    assert params["spatial-augmentation"] == "low"
    assert params["freeze-backbone"] == "false"
    assert "color-space-augmentation=medium" in label


def test_spatial_augmentation_override_applied():
    _label, _visual, params = eitv.select_model(
        "proj",
        "key",
        "yolo-pro",
        yolo_variant="no_attn_relu",
        yolo_sizing="medium",
        spatial_augmentation="medium",
    )
    assert params["spatial-augmentation"] == "medium"
    assert params["color-space-augmentation"] == "low"


def test_freeze_backbone_override_applied():
    _label, _visual, params = eitv.select_model(
        "proj",
        "key",
        "yolo-pro",
        yolo_variant="no_attn_relu",
        yolo_sizing="medium",
        freeze_backbone="true",
    )
    assert params["freeze-backbone"] == "true"


def test_all_three_overrides_applied_together():
    label, _visual, params = eitv.select_model(
        "proj",
        "key",
        "yolo-pro",
        yolo_variant="no_attn_relu",
        yolo_sizing="medium",
        freeze_backbone="true",
        spatial_augmentation="high",
        color_space_augmentation="high",
    )
    assert params["freeze-backbone"] == "true"
    assert params["spatial-augmentation"] == "high"
    assert params["color-space-augmentation"] == "high"
    for bit in ("freeze-backbone=true", "spatial-augmentation=high", "color-space-augmentation=high"):
        assert bit in label


def test_invalid_color_space_augmentation_rejected():
    """A value outside the live selectOptions ladder fails loudly, not silently."""
    with pytest.raises(ValueError, match="color_space_augmentation must be one of"):
        eitv.select_model(
            "proj",
            "key",
            "yolo-pro",
            yolo_variant="no_attn_relu",
            yolo_sizing="medium",
            color_space_augmentation="extreme",
        )


def test_invalid_spatial_augmentation_rejected():
    with pytest.raises(ValueError, match="spatial_augmentation must be one of"):
        eitv.select_model(
            "proj",
            "key",
            "yolo-pro",
            yolo_variant="no_attn_relu",
            yolo_sizing="medium",
            spatial_augmentation="ultra",
        )


def test_invalid_freeze_backbone_rejected():
    """freeze-backbone is a flag - only 'true'/'false' are valid, not e.g. '1'."""
    with pytest.raises(ValueError, match="freeze_backbone must be one of"):
        eitv.select_model(
            "proj",
            "key",
            "yolo-pro",
            yolo_variant="no_attn_relu",
            yolo_sizing="medium",
            freeze_backbone="1",
        )


def test_overrides_ignored_for_non_yolo_pro_family():
    """fomo/ssd never look at customParameters at all - passing overrides for
    them is a no-op, not an error, since main() always threads all three
    through regardless of --family.
    """
    label, _visual, params = eitv.select_model(
        "proj",
        "key",
        "fomo",
        freeze_backbone="true",
        spatial_augmentation="high",
        color_space_augmentation="high",
    )
    assert params == {}
    assert "freeze" not in label


def test_missing_param_definition_raises_runtime_error():
    """If Edge Impulse ever drops one of these three customParameters entirely,
    fail loudly rather than silently skip the override.
    """
    model = _yolo_pro_model()
    model["customParameters"] = [
        p for p in model["customParameters"] if p["param"] != "freeze-backbone"
    ]

    def fake_request(path, api_key, method="GET", body=None, timeout=180, retries=3):
        return {"transferLearningModels": [model]}

    import edge_impulse_train_vision as module

    module.request = fake_request
    try:
        with pytest.raises(RuntimeError, match="no 'freeze-backbone'"):
            module.select_model(
                "proj",
                "key",
                "yolo-pro",
                yolo_variant="no_attn_relu",
                yolo_sizing="medium",
                freeze_backbone="true",
            )
    finally:
        del module.request
