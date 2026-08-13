"""M6 脚本验收测试。

验证 scripts/k12_preflight.py 和 scripts/k12_demo_seed.py 的核心功能：
- 数据结构和报告生成
- 环境检查函数不崩溃
- 演示种子脚本的画像创建和重置逻辑
- 脚本可被 importlib 正确加载
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "scripts"


def _load_script(module_name: str, filename: str):
    """从 scripts/ 目录加载脚本模块。"""
    path = SCRIPTS_DIR / filename
    if not path.exists():
        pytest.skip(f"{filename} not found")
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    # 在 exec 之前注册到 sys.modules，使 dataclass 装饰器能找到模块
    sys.modules[module_name] = module
    # 脚本会向 sys.path 插入 ROOT，确保可导入 deeptutor
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def preflight_module():
    return _load_script("k12_preflight_test", "k12_preflight.py")


@pytest.fixture(scope="module")
def demo_seed_module():
    return _load_script("k12_demo_seed_test", "k12_demo_seed.py")


# ── PreflightReport 数据结构测试 ──


class TestPreflightReport:
    def test_report_add_and_passed(self, preflight_module):
        PreflightReport = preflight_module.PreflightReport
        report = PreflightReport()
        report.add("test_pass", True, required=True, detail="ok")
        report.add("test_fail", False, required=True, detail="bad")
        report.add("test_warn", False, required=False, detail="optional")
        assert len(report.results) == 3
        assert report.all_required_passed is False  # 有一个必需项失败

    def test_report_all_required_passed_when_all_ok(self, preflight_module):
        PreflightReport = preflight_module.PreflightReport
        report = PreflightReport()
        report.add("a", True, required=True)
        report.add("b", True, required=True)
        report.add("c", False, required=False)  # 可选项失败不影响
        assert report.all_required_passed is True

    def test_report_to_dict(self, preflight_module):
        PreflightReport = preflight_module.PreflightReport
        report = PreflightReport()
        report.add("a", True, required=True, detail="ok")
        d = report.to_dict()
        assert d["all_required_passed"] is True
        assert len(d["results"]) == 1
        assert d["results"][0]["name"] == "a"
        assert d["results"][0]["passed"] is True


# ── 环境检查函数测试（不崩溃即可）──


class TestPreflightChecks:
    def test_check_python_version(self, preflight_module):
        report = preflight_module.PreflightReport()
        preflight_module.check_python_version(report)
        assert len(report.results) == 1
        assert report.results[0].passed is True  # 当前 Python 必然 >= 3.11
        assert report.results[0].name == "Python 版本 (>= 3.11)"

    def test_check_node_version(self, preflight_module):
        report = preflight_module.PreflightReport()
        preflight_module.check_node_version(report)
        assert len(report.results) == 1
        # Node 可能未安装，但不应崩溃
        assert report.results[0].name == "Node 版本 (>= 20)"

    def test_check_k12_catalog(self, preflight_module):
        report = preflight_module.PreflightReport()
        preflight_module.check_k12_catalog(report)
        assert len(report.results) == 1
        # catalog v2 存在且通过
        assert report.results[0].passed is True

    def test_check_disk_space(self, preflight_module):
        report = preflight_module.PreflightReport()
        preflight_module.check_disk_space(report)
        assert len(report.results) == 1
        assert report.results[0].passed is True  # 磁盘空间充足

    def test_check_web_build(self, preflight_module, monkeypatch, tmp_path):
        class _PathService:
            project_root = tmp_path

        monkeypatch.setattr(preflight_module, "_path_service", lambda: _PathService())

        missing_report = preflight_module.PreflightReport()
        preflight_module.check_web_build(missing_report)
        assert len(missing_report.results) == 1
        assert missing_report.results[0].passed is False
        assert "npm run build" in missing_report.results[0].suggestion

        build_id = tmp_path / "web" / ".next" / "BUILD_ID"
        build_id.parent.mkdir(parents=True)
        build_id.write_text("ci-test-build", encoding="utf-8")

        built_report = preflight_module.PreflightReport()
        preflight_module.check_web_build(built_report)
        assert len(built_report.results) == 1
        assert built_report.results[0].passed is True
        assert "ci-test-build" in built_report.results[0].detail

    def test_check_model_config(self, preflight_module):
        report = preflight_module.PreflightReport()
        preflight_module.check_model_config(report)
        assert len(report.results) == 2
        assert {item.name for item in report.results} == {
            "LLM Provider",
            "Embedding Provider",
        }
        # 不应崩溃，可能通过也可能不通过

    def test_check_sandbox(self, preflight_module):
        report = preflight_module.PreflightReport()
        preflight_module.check_sandbox(report)
        assert len(report.results) == 1
        # 不应崩溃

    def test_check_ports(self, preflight_module):
        report = preflight_module.PreflightReport()
        preflight_module.check_ports(report, backend_port=8001, frontend_port=3782)
        assert len(report.results) >= 1
        # 不应崩溃

    def test_check_data_dir_writable(self, preflight_module):
        report = preflight_module.PreflightReport()
        preflight_module.check_data_dir_writable(report)
        assert len(report.results) == 1
        # 不应崩溃

    def test_check_optional_capabilities(self, preflight_module):
        report = preflight_module.PreflightReport()
        preflight_module.check_optional_capabilities(report, 8001, False)
        # 应检查 Voice 和 Manim
        names = [r.name for r in report.results]
        assert any("Voice" in n or "语音" in n for n in names)


# ── demo_seed 脚本测试 ──


class TestDemoSeed:
    def test_reset_demo_progress_no_file(self, demo_seed_module, tmp_path):
        """重置时如果事件文件不存在，应返回无需重置。"""
        result = demo_seed_module.reset_demo_progress(
            events_path=tmp_path / "education_events.json",
            episodes_path=tmp_path / "education_episodes.json",
            learning_root=tmp_path / "learning",
        )
        assert isinstance(result, dict)
        assert "action" in result
        assert result["action"] == "reset_demo_progress"
        assert "deleted" in result
        # 如果文件不存在，deleted 应为 False
        if not result.get("deleted"):
            assert "message" in result or "path" in result

    def test_create_demo_profile_returns_dict(self, demo_seed_module, tmp_path):
        """create_demo_profile 应返回包含 profile 和 path 的 dict。"""
        # 注意：在沙箱环境中可能因权限失败，但函数签名应正确
        try:
            from deeptutor.education.profile_service import EducationProfileService

            result = demo_seed_module.create_demo_profile(
                EducationProfileService(tmp_path / "profile.json")
            )
            assert isinstance(result, dict)
        except PermissionError:
            # 沙箱限制，跳过
            pytest.skip("沙箱限制无法写入文件")

    def test_demo_profile_has_correct_stage(self, demo_seed_module, tmp_path):
        """演示画像应为小学高年级五年级。"""
        from deeptutor.education.models import EducationStage

        try:
            from deeptutor.education.profile_service import EducationProfileService

            service = EducationProfileService(tmp_path / "profile.json")
            result = demo_seed_module.create_demo_profile(service)
            profile = service.load()
            assert result["stage"] == EducationStage.PRIMARY_UPPER.value
            assert profile is not None
            assert profile.stage == EducationStage.PRIMARY_UPPER
            assert profile.grade == 5
            assert profile.textbook_id == "k12-ai-primary-upper"
        except PermissionError:
            pytest.skip("沙箱限制无法写入文件")
