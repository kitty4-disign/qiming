#!/usr/bin/env python
"""One-command setup for the four stage-specific K12 textbook knowledge bases."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Ensure path/config resolution stays inside this checkout.
os.environ.setdefault("DEEPTUTOR_HOME", str(ROOT))

from deeptutor.education.knowledge_bootstrap import ensure_all_k12_knowledge_bases
from deeptutor.services.rag.factory import DEFAULT_PROVIDER


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create/reindex the four K12 AI literacy textbook knowledge bases."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild even if a ready index already exists.",
    )
    parser.add_argument(
        "--skip-index",
        action="store_true",
        help="Copy textbook sources only; skip embedding/indexing.",
    )
    parser.add_argument(
        "--provider",
        default=DEFAULT_PROVIDER,
        help=f"RAG provider to bind (default: {DEFAULT_PROVIDER}).",
    )
    args = parser.parse_args()
    results = asyncio.run(
        ensure_all_k12_knowledge_bases(
            force=args.force,
            process=not args.skip_index,
            rag_provider=args.provider,
        )
    )
    failed = 0
    for item in results:
        print(f"{item.name}\t{item.action}\t{item.status}\t{item.detail}")
        if item.status != "ready":
            failed += 1
    if failed:
        print(f"ERROR: {failed} knowledge base(s) failed", file=sys.stderr)
        print(
            "Hint: set a real embedding model in Settings > Catalog "
            "(not a chat model). For Agnes gateways, base_url should usually be "
            "https://apihub.agnes-ai.com/v1/embeddings and send_dimensions=false.",
            file=sys.stderr,
        )
        print(
            "Sources may already be copied under data/knowledge_bases/*/raw/. "
            "After fixing embedding, re-run with --force.",
            file=sys.stderr,
        )
        return 1
    print("OK: all four K12 textbook knowledge bases are ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
