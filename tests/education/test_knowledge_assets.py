from pathlib import Path

import yaml


def test_every_catalog_kb_has_a_source_document():
    root = Path(__file__).resolve().parents[2]
    catalog = yaml.safe_load((root / "deeptutor/education/catalog.yaml").read_text("utf-8"))
    assets = {path.stem for path in (root / "assets/k12-knowledge").glob("*.md")}
    expected = {
        "primary-lower-ai-first-steps",
        "primary-upper-image-recognition",
        "middle-classification-lab",
        "high-python-image-classifier",
    }
    assert assets == expected
    assert len(catalog["textbooks"]) == 4


def test_assets_contain_learning_objectives_safety_and_sources():
    root = Path(__file__).resolve().parents[2] / "assets/k12-knowledge"
    for path in root.glob("*.md"):
        text = path.read_text("utf-8")
        assert "## 学习目标" in text
        assert "## 核心知识" in text
        assert "## 练习" in text
        assert "## 安全与伦理" in text
        assert "## 参考来源" in text
