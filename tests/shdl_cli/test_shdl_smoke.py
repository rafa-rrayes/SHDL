"""Subprocess smoke: the console entry point behaves at the process level."""

from __future__ import annotations

import os
import subprocess
import sys


def _shdl(args, cwd, extra_env=None):
    env = dict(os.environ)
    env.pop("SHDL_INDEX_URL", None)
    env.update(extra_env or {})
    return subprocess.run(
        [sys.executable, "-m", "shdl_cli.cli", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )


def test_help_exits_zero(tmp_path):
    proc = _shdl(["--help"], tmp_path)
    assert proc.returncode == 0
    assert "SHDL project manager" in proc.stdout


def test_usage_error_exits_two(tmp_path):
    assert _shdl(["bogus-command"], tmp_path).returncode == 2
    assert _shdl([], tmp_path).returncode == 2


def test_new_add_build_via_env_index(tmp_path, registry_url):
    env = {"SHDL_INDEX_URL": registry_url}
    assert _shdl(["new", "demo"], tmp_path, env).returncode == 0
    demo = tmp_path / "demo"
    add = _shdl(["add", "adders"], demo, env)
    assert add.returncode == 0, add.stderr
    assert "fetched nands 0.1.0" in add.stdout
    build = _shdl(["build", "--dev"], demo, env)
    assert build.returncode == 0, build.stderr
    assert (demo / "build").is_dir()
    outside = _shdl(["build"], tmp_path, env)
    assert outside.returncode == 1
    assert "no shdl.toml" in outside.stderr
