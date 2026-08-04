from pathlib import Path

import pytest

from deeptutor.education.knowledge_bootstrap import (
    K12_KB_SOURCE_STEMS,
    ensure_all_k12_knowledge_bases,
    expected_k12_targets,
)
from deeptutor.knowledge.manager import KnowledgeBaseManager


def test_expected_targets_map_to_existing_assets():
    targets = expected_k12_targets()
    assert [item.name for item in targets] == list(K12_KB_SOURCE_STEMS)
    for target in targets:
        assert target.source_path.exists()
        assert target.source_path.suffix == ".md"


@pytest.mark.asyncio
async def test_prepare_only_copies_all_four_sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "project"
    assets = root / "assets" / "k12-knowledge"
    assets.mkdir(parents=True)
    kb_root = root / "data" / "knowledge_bases"
    kb_root.mkdir(parents=True)

    # Point package assets and catalog sources through a temporary tree by
    # copying the four markdown files and patching path helpers.
    from deeptutor.education import knowledge_bootstrap as bootstrap

    real_assets = Path(__file__).resolve().parents[2] / "assets" / "k12-knowledge"
    for source in real_assets.glob("*.md"):
        (assets / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    monkeypatch.setattr(bootstrap, "project_root", lambda: root)
    monkeypatch.setattr(bootstrap, "assets_root", lambda r=None: assets)
    monkeypatch.setattr(bootstrap, "kb_base_dir", lambda r=None: kb_root)

    manager = KnowledgeBaseManager(base_dir=str(kb_root))
    results = await ensure_all_k12_knowledge_bases(
        root=root,
        manager=manager,
        process=False,
        force=True,
    )
    assert len(results) == 4
    assert all(item.status == "ready" for item in results)
    assert all(item.action == "prepared" for item in results)
    for name, stem in K12_KB_SOURCE_STEMS.items():
        assert (kb_root / name / "raw" / f"{stem}.md").exists()
