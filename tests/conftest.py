"""
pytest fixtures for weflow.

Key goals:
- Tests must run **without** real WeChat credentials.
- All network calls are monkeypatched to raise so accidental real HTTP
  during tests fails loudly instead of silently hitting the internet.
- `engine/` directory is added to sys.path so tests can `import config`,
  `import ai_score`, `import html_converter` directly.
- Project root is also added so `from engine.xxx import yyy` works.
"""

from __future__ import annotations

import os
import sys
import textwrap
from pathlib import Path

# 测试环境：在导入任何项目模块之前设置日志级别，避免控制台日志干扰 pytest 输出。
# logger.py 的 setup_logging() 会在首次 get_logger() 时读取此环境变量。
os.environ.setdefault("WEFLOW_LOG_LEVEL", "ERROR")

import pytest

# Make engine/ importable for all test files (engine is under backend/).
_PROJECT_ROOT = Path(__file__).parent.parent
_BACKEND_DIR = _PROJECT_ROOT / "backend"
_ENGINE_DIR = _BACKEND_DIR / "engine"
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))
if str(_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(_ENGINE_DIR))


# ---------------------------------------------------------------------------
# config.yaml fixture
# ---------------------------------------------------------------------------

# Minimal but realistic config.yaml content.
# Just enough for config.py to parse successfully. No real credentials.
_MIN_CONFIG_YAML = textwrap.dedent(
    """\
    default: main

    accounts:
      main:
        name: "Test Main"
        app_id: "wx_fake_main_app_id_0001"
        app_secret: "fake_main_secret"
        author: "作者A"
        theme: "refined-blue"
        voice: "test-voice-main"

      tech:
        name: "Test Tech"
        app_id: "wx_fake_tech_app_id_0002"
        app_secret: "fake_tech_secret"
        author: "作者B"
        theme: "minimal-mono"
        voice: "test-voice-tech"
    """
)


@pytest.fixture
def tmp_config_yaml(tmp_path, monkeypatch):
    """
    Drop a minimal `config.yaml` into a temp directory.

    Yields the parsed dict (handy when tests want to double-check what's in
    the file they're testing against).
    """
    import yaml

    yaml_path = tmp_path / "config.yaml"
    yaml_path.write_text(_MIN_CONFIG_YAML, encoding="utf-8")

    # Reset any active account set by a previous test.
    try:
        import config
        config.set_account(None)
        monkeypatch.setattr(config, "_config_path", lambda: yaml_path)
    except ImportError:
        pass

    data = yaml.safe_load(_MIN_CONFIG_YAML)
    yield data

    # Teardown: clear active account again so leakage doesn't affect later tests.
    try:
        import config
        config.set_account(None)
    except ImportError:
        pass


@pytest.fixture
def write_config_yaml(tmp_path, monkeypatch):
    """
    Like `tmp_config_yaml` but returns a writer function so a test can
    supply custom YAML content.
    """
    try:
        import config
        config.set_account(None)
    except ImportError:
        pass

    def _write(yaml_text: str) -> Path:
        p = tmp_path / "config.yaml"
        p.write_text(yaml_text, encoding="utf-8")
        try:
            import config
            config.set_account(None)
            monkeypatch.setattr(config, "_config_path", lambda: p)
        except ImportError:
            pass
        return p

    yield _write

    try:
        import config
        config.set_account(None)
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Network blocker
# ---------------------------------------------------------------------------

@pytest.fixture
def no_network(monkeypatch):
    """
    Monkeypatch requests.get / requests.post to raise so the test fails
    loudly if a code path accidentally hits the real WeChat API.

    Usage:
        def test_thing(no_network):
            ...  # if requests.get is called, RuntimeError is raised
    """
    def _boom(*args, **kwargs):
        raise RuntimeError(
            "Accidental network call in a unit test — mock this explicitly."
        )

    try:
        import requests
        monkeypatch.setattr(requests, "get", _boom)
        monkeypatch.setattr(requests, "post", _boom)
    except ImportError:
        # requests not installed — nothing to block.
        pass

    # Also block urllib just in case.
    try:
        import urllib.request
        monkeypatch.setattr(urllib.request, "urlopen", _boom)
    except ImportError:
        pass

    yield
