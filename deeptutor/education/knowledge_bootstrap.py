from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from deeptutor.education.catalog import load_catalog
from deeptutor.knowledge.initializer import KnowledgeBaseInitializer
from deeptutor.knowledge.manager import KnowledgeBaseManager
from deeptutor.runtime.home import PACKAGE_ROOT
from deeptutor.services.rag.factory import DEFAULT_PROVIDER
from deeptutor.services.rag.index_probe import has_ready_provider_index

# Catalog KB name -> textbook markdown under assets/k12-knowledge/
K12_KB_SOURCE_STEMS: dict[str, str] = {
    "k12-ai-primary-lower": "primary-lower-ai-first-steps",
    "k12-ai-primary-upper": "primary-upper-image-recognition",
    "k12-ai-middle": "middle-classification-lab",
    "k12-ai-high": "high-python-image-classifier",
}


@dataclass(frozen=True)
class K12KnowledgeTarget:
    name: str
    source_path: Path


@dataclass
class K12KnowledgeResult:
    name: str
    action: str
    status: str
    detail: str = ""


def project_root() -> Path:
    # Always pin to the package checkout so CLI/scripts do not pick up an
    # ambient DEEPTUTOR_HOME that points at a parent directory.
    return PACKAGE_ROOT


def assets_root(root: Path | None = None) -> Path:
    return (root or project_root()) / "assets" / "k12-knowledge"


def kb_base_dir(root: Path | None = None) -> Path:
    return (root or project_root()) / "data" / "knowledge_bases"


def expected_k12_targets(root: Path | None = None) -> list[K12KnowledgeTarget]:
    """Return the four stage KBs in catalog order with resolved source files."""
    root = root or project_root()
    catalog = load_catalog()
    assets = assets_root(root)
    targets: list[K12KnowledgeTarget] = []
    for textbook in catalog.textbooks:
        stem = K12_KB_SOURCE_STEMS.get(textbook.knowledge_base)
        if not stem:
            raise ValueError(
                f"No source mapping for catalog knowledge base '{textbook.knowledge_base}'"
            )
        source = assets / f"{stem}.md"
        if not source.exists():
            raise FileNotFoundError(f"Missing K12 textbook asset: {source}")
        targets.append(K12KnowledgeTarget(name=textbook.knowledge_base, source_path=source))
    missing = set(K12_KB_SOURCE_STEMS) - {item.name for item in targets}
    if missing:
        raise ValueError(f"Catalog is missing expected K12 knowledge bases: {sorted(missing)}")
    return targets


def _source_is_present(kb_dir: Path, source_path: Path) -> bool:
    raw_file = kb_dir / "raw" / source_path.name
    return raw_file.exists() and raw_file.is_file()


def _is_ready(manager: KnowledgeBaseManager, name: str, provider: str) -> bool:
    entry = (manager.config.get("knowledge_bases") or {}).get(name) or {}
    status = str(entry.get("status") or "").lower()
    if status in {"error", "initializing", "processing"}:
        return False
    kb_dir = Path(manager.base_dir) / name
    return has_ready_provider_index(kb_dir, provider)


async def ensure_k12_knowledge_base(
    target: K12KnowledgeTarget,
    *,
    manager: KnowledgeBaseManager | None = None,
    rag_provider: str = DEFAULT_PROVIDER,
    force: bool = False,
    process: bool = True,
) -> K12KnowledgeResult:
    """Create/reindex one K12 textbook knowledge base if needed."""
    mgr = manager or KnowledgeBaseManager(base_dir=str(kb_base_dir()))
    provider = rag_provider or DEFAULT_PROVIDER
    kb_dir = Path(mgr.base_dir) / target.name
    exists = target.name in mgr.list_knowledge_bases() or kb_dir.exists()

    if (
        exists
        and not force
        and _source_is_present(kb_dir, target.source_path)
        and _is_ready(mgr, target.name, provider)
    ):
        return K12KnowledgeResult(
            name=target.name,
            action="skipped",
            status="ready",
            detail="already indexed",
        )

    initializer = KnowledgeBaseInitializer(
        kb_name=target.name,
        base_dir=str(mgr.base_dir),
        rag_provider=provider,
    )
    initializer.create_directory_structure()
    copied = initializer.copy_documents([str(target.source_path)])
    if not copied:
        return K12KnowledgeResult(
            name=target.name,
            action="failed",
            status="error",
            detail=f"failed to copy source document: {target.source_path}",
        )

    if not process:
        mgr.update_kb_status(
            name=target.name,
            status="ready",
            progress={
                "stage": "completed",
                "message": "Source document prepared (indexing skipped)",
                "percent": 100,
                "current": 1,
                "total": 1,
                "file_name": target.source_path.name,
                "error": None,
                "timestamp": datetime.now().isoformat(),
                "indexed_count": 1,
                "index_changed": False,
                "index_action": "prepare",
            },
        )
        return K12KnowledgeResult(
            name=target.name,
            action="prepared",
            status="ready",
            detail="source copied; indexing skipped",
        )

    try:
        await initializer.process_documents()
    except Exception as exc:
        mgr.update_kb_status(
            name=target.name,
            status="error",
            progress={
                "stage": "error",
                "message": "K12 knowledge base initialization failed",
                "percent": 0,
                "current": 0,
                "total": 1,
                "file_name": target.source_path.name,
                "error": str(exc),
                "timestamp": datetime.now().isoformat(),
            },
        )
        return K12KnowledgeResult(
            name=target.name,
            action="failed",
            status="error",
            detail=str(exc),
        )

    mgr.update_kb_status(
        name=target.name,
        status="ready",
        progress={
            "stage": "completed",
            "message": "Knowledge base initialization complete!",
            "percent": 100,
            "current": 1,
            "total": 1,
            "file_name": target.source_path.name,
            "error": None,
            "timestamp": datetime.now().isoformat(),
            "indexed_count": 1,
            "index_changed": True,
            "index_action": "create" if not exists else "reindex",
        },
    )
    return K12KnowledgeResult(
        name=target.name,
        action="created" if not exists else "reindexed",
        status="ready",
        detail=target.source_path.name,
    )


async def ensure_all_k12_knowledge_bases(
    *,
    root: Path | None = None,
    manager: KnowledgeBaseManager | None = None,
    rag_provider: str = DEFAULT_PROVIDER,
    force: bool = False,
    process: bool = True,
    targets: Iterable[K12KnowledgeTarget] | None = None,
) -> list[K12KnowledgeResult]:
    """Ensure all four stage-specific textbook knowledge bases are ready."""
    root = root or project_root()
    mgr = manager or KnowledgeBaseManager(base_dir=str(kb_base_dir(root)))
    resolved = list(targets) if targets is not None else expected_k12_targets(root)
    results: list[K12KnowledgeResult] = []
    for target in resolved:
        results.append(
            await ensure_k12_knowledge_base(
                target,
                manager=mgr,
                rag_provider=rag_provider,
                force=force,
                process=process,
            )
        )
    return results


__all__ = [
    "K12_KB_SOURCE_STEMS",
    "K12KnowledgeResult",
    "K12KnowledgeTarget",
    "assets_root",
    "ensure_all_k12_knowledge_bases",
    "ensure_k12_knowledge_base",
    "expected_k12_targets",
    "kb_base_dir",
]
