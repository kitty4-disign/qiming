#!/usr/bin/env python
"""K12 竞赛演示种子数据与复位脚本。

功能：
1. 创建演示画像（小学高年级五年级）
2. 初始化四个课程知识库
3. 可选重置演示账号的 K12 学习进度（需 --reset-demo-progress）

不影响其他用户和非 K12 数据。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("DEEPTUTOR_HOME", str(ROOT))

try:
    from deeptutor.education.activity_service import EducationActivityService
    from deeptutor.education.knowledge_bootstrap import ensure_all_k12_knowledge_bases
    from deeptutor.education.models import EducationStage, StudentProfile
    from deeptutor.education.path_ids import build_mastery_path_id
    from deeptutor.education.profile_service import EducationProfileService
    from deeptutor.education.catalog import load_catalog
    from deeptutor.services.path_service import get_path_service
except ImportError as exc:
    print(f"[k12_demo_seed] 无法导入 DeepTutor 模块: {exc}", file=sys.stderr)
    print(
        "请确认在 DeepTutor 项目根目录运行此脚本，或已安装 deeptutor 包。",
        file=sys.stderr,
    )
    raise SystemExit(2)


def create_demo_profile(service: EducationProfileService | None = None) -> dict:
    """创建小学高年级五年级演示画像并保存。

    返回包含画像摘要与保存路径的字典。
    """
    profile = StudentProfile(
        stage=EducationStage.PRIMARY_UPPER,
        grade=5,
        textbook_id="k12-ai-primary-upper",
        interests=["机器人", "画画"],
        preferred_modalities=["dialogue", "quiz", "animation"],
        learning_goal="学会图像识别的基本原理",
        display_name="演示同学",
    )
    service = service or EducationProfileService()
    service.save(profile)
    return {
        "action": "create_profile",
        "path": str(service.path),
        "display_name": profile.display_name,
        "stage": profile.stage.value,
        "grade": profile.grade,
        "textbook_id": profile.textbook_id,
        "interests": list(profile.interests),
        "preferred_modalities": list(profile.preferred_modalities),
        "learning_goal": profile.learning_goal,
    }


def init_knowledge_bases(force: bool, skip_index: bool) -> dict:
    """初始化四个课程知识库。

    force: 强制重建索引。
    skip_index: 仅复制源文件，不建立索引。
    返回每个知识库的 name/action/status/detail 及失败计数。
    """
    results = asyncio.run(
        ensure_all_k12_knowledge_bases(
            force=force,
            process=not skip_index,
            rag_provider="llamaindex",
        )
    )
    items = [
        {
            "name": r.name,
            "action": r.action,
            "status": r.status,
            "detail": r.detail,
        }
        for r in results
    ]
    failed = sum(1 for r in results if r.status != "ready")
    return {
        "action": "init_knowledge_bases",
        "force": force,
        "skip_index": skip_index,
        "results": items,
        "failed": failed,
    }


def reset_demo_progress(
    *,
    events_path: Path | None = None,
    episodes_path: Path | None = None,
    learning_root: Path | None = None,
) -> dict:
    """重置演示账号 K12 学习进度。

    仅删除学习事件文件（education_events.json），不删除画像、不删除知识库、
    不影响其他用户。文件不存在时提示无需重置。
    """
    path_service = get_path_service()
    path = events_path or EducationActivityService().path
    k12_paths = {
        build_mastery_path_id(textbook.id, course.id)
        for textbook in load_catalog().textbooks
        for course in textbook.courses
    }
    removed: list[str] = []
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        retained = [
            event for event in payload.get("events", [])
            if event.get("mastery_path_id") not in k12_paths
        ]
        if retained:
            path.write_text(
                json.dumps({"events": retained}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        else:
            path.unlink()
        removed.append(str(path))
    episodes_path = episodes_path or path_service.get_settings_file("education_episodes")
    if episodes_path.exists():
        episodes_path.unlink()
        removed.append(str(episodes_path))
    learning_root = learning_root or (path_service.get_workspace_dir() / "learning")
    for path_id in k12_paths:
        mastery_path = learning_root / f"{path_id}.json"
        if mastery_path.exists():
            mastery_path.unlink()
            removed.append(str(mastery_path))
    if removed:
        return {
            "action": "reset_demo_progress",
            "path": str(path),
            "paths": removed,
            "deleted": True,
            "message": f"已重置 {len(removed)} 个 K12 学习状态文件",
        }
    return {
        "action": "reset_demo_progress",
        "path": str(path),
        "deleted": False,
        "message": "无需重置：当前用户没有 K12 学习状态",
    }


def _print_profile(result: dict) -> None:
    print("[画像] 已创建演示画像")
    print(f"  路径        : {result['path']}")
    print(f"  显示名      : {result['display_name']}")
    print(f"  学段        : {result['stage']}")
    print(f"  年级        : {result['grade']}")
    print(f"  教材 ID     : {result['textbook_id']}")
    print(f"  兴趣        : {', '.join(result['interests'])}")
    print(f"  偏好模态    : {', '.join(result['preferred_modalities'])}")
    print(f"  学习目标    : {result['learning_goal']}")


def _print_knowledge_bases(result: dict) -> None:
    if result["skip_index"]:
        print("[知识库] 仅复制源文件，未建立索引（--skip-index）")
    else:
        label = "强制重建" if result["force"] else "初始化"
        print(f"[知识库] {label}四个课程知识库")
    print("  名称                          动作         状态     详情")
    for item in result["results"]:
        print(
            f"  {item['name']:<30} {item['action']:<12} {item['status']:<8} {item['detail']}"
        )
    total = len(result["results"])
    failed = result["failed"]
    print(f"  共 {total} 个知识库，失败 {failed} 个")


def _print_reset(result: dict) -> None:
    print("[重置] 演示账号 K12 学习进度")
    if result["deleted"]:
        print(f"  已删除文件  : {result['path']}")
    else:
        print(f"  无需重置    : {result['path']}（文件不存在）")
    print("  说明        : 重置当前用户的 K12 活动、Episode 和掌握度，不影响非 K12 数据")


def _emit(report: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    if "profile" in report:
        _print_profile(report["profile"])
        print()
    if "knowledge_bases" in report:
        _print_knowledge_bases(report["knowledge_bases"])
        print()
    if "reset" in report:
        _print_reset(report["reset"])
        print()
    print(f"完成（退出码 {report['exit_code']}）")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="K12 竞赛演示种子数据与复位脚本。",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制重建知识库索引（即使已存在就绪索引）。",
    )
    parser.add_argument(
        "--skip-index",
        action="store_true",
        help="仅复制源文件，不建立索引（用于结构测试）。",
    )
    parser.add_argument(
        "--reset-demo-progress",
        action="store_true",
        help="重置演示账号 K12 学习进度（破坏性操作，需明确参数）。"
        "指定后只执行重置，不创建画像或知识库。",
    )
    parser.add_argument(
        "--profile-only",
        action="store_true",
        help="仅创建演示画像，不初始化知识库。",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 格式输出结果。",
    )
    args = parser.parse_args()

    report: dict = {"actions": [], "exit_code": 0}

    # 破坏性操作优先：仅执行重置，不创建画像或知识库。
    if args.reset_demo_progress:
        result = reset_demo_progress()
        report["reset"] = result
        report["actions"].append("reset_demo_progress")
        _emit(report, args.json)
        return 0

    # 默认行为：创建演示画像。
    profile_result = create_demo_profile()
    report["profile"] = profile_result
    report["actions"].append("create_profile")

    # --profile-only 时跳过知识库初始化。
    if not args.profile_only:
        kb_result = init_knowledge_bases(args.force, args.skip_index)
        report["knowledge_bases"] = kb_result
        report["actions"].append("init_knowledge_bases")
        if kb_result["failed"]:
            report["exit_code"] = 1

    _emit(report, args.json)
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
