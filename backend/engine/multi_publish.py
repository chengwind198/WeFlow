#!/usr/bin/env python3
"""
多平台同步发布 - Wechatsync CLI 封装

把 Markdown 文章同步到知乎 / 掘金 / CSDN / 头条等平台（各平台存为草稿）。
底层调用 `@wechatsync/cli`,本脚本只负责：
  - 前置检查(CLI 是否已装、MCP Token 是否配置、图片路径是否可同步)
  - 透传调用
  - 结果归一化

前置条件(一次性)：
  1. 安装 Chrome 扩展 Wechatsync 并登录各目标平台
  2. 扩展设置里启用「MCP 连接」并拷出 Token
  3. npm install -g @wechatsync/cli
  4. config.yaml 加 integrations.wechatsync_mcp_token

用法：
    python multi_publish.py --input article.md --platforms zhihu,juejin,csdn
    python multi_publish.py --input article.md --platforms zhihu --title "自定义"
    python multi_publish.py --check   # 仅做环境检查,不发布
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from engine.logger import get_logger

try:
    from engine.config import load_env
except ImportError:
    load_env = None

logger = get_logger(__name__)


from engine.constants import SyncPlatform

SUPPORTED_PLATFORMS = set(SyncPlatform.all_codes())


def _get_wechatsync_version(cli_path):
    """
    尝试读取 wechatsync CLI 的版本号。
    子命令不存在或超时都返回 None,不让检查流程挂掉。
    """
    if not cli_path:
        return None
    try:
        proc = subprocess.run(
            [cli_path, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if proc.returncode != 0:
        return None
    out = (proc.stdout or proc.stderr or "").strip()
    return out.splitlines()[0] if out else None


def check_prerequisites(verbose=True):
    """
    检查运行前置条件,返回 (ok, problems[])。

    任何一项失败都会让 problems 里多一条;但同步不强制每项都过
    （例如 CLI 没装会直接阻断,token 没配则只 warn）。
    """
    problems = []
    if load_env:
        load_env()

    # 1. wechatsync CLI
    cli_path = shutil.which("wechatsync")
    if not cli_path:
        logger.warning("未找到 wechatsync CLI")
        problems.append(
            "未找到 wechatsync CLI。请先执行: npm install -g @wechatsync/cli"
        )
    elif verbose:
        version = _get_wechatsync_version(cli_path)
        if version:
            print(f"  ✓ wechatsync CLI: {cli_path} ({version})")
        else:
            print(f"  ✓ wechatsync CLI: {cli_path} (版本查询失败,可能不支持 --version)")

    # 2. MCP Token
    token = os.environ.get("WECHATSYNC_TOKEN", "").strip()
    if not token:
        logger.warning("未配置 WECHATSYNC_TOKEN")
        problems.append(
            "未配置 WECHATSYNC_TOKEN。请在 Chrome 扩展的 MCP 设置里生成 Token,"
            "并写入 config.yaml 的 integrations.wechatsync_mcp_token"
        )
    elif verbose:
        print(f"  ✓ WECHATSYNC_TOKEN: {token[:6]}...")

    return len(problems) == 0, problems


def compute_default_timeout(platforms):
    """
    根据平台数量推算同步子进程超时(秒)。
    公式:60 + 60 * n,上下限 [120, 900]。
    """
    n = len(platforms) if platforms else 1
    base = 60 + 60 * n
    return max(120, min(base, 900))


def scan_local_images(md_content):
    """
    扫 markdown 里的图片引用,区分 '外部 URL' 和 '本地路径'。

    wechatsync 对外部 URL 通常能自动转存到各目标平台;本地绝对路径
    的处理能力目前文档未明确,**可能**同步失败。这里只负责提醒,不做转换。

    Returns:
        (local_paths, remote_urls): 两个 list
    """
    pattern = r"!\[[^\]]*\]\(([^)]+)\)"
    refs = re.findall(pattern, md_content)
    local, remote = [], []
    for url in refs:
        url = url.strip()
        if url.startswith(("http://", "https://")):
            remote.append(url)
        else:
            local.append(url)
    return local, remote


def _find_wechatsync() -> str | None:
    """查找 wechatsync CLI 可执行文件的全路径。

    按优先级尝试: 1) shutil.which('wechatsync')
                 2) shutil.which('wechatsync.cmd')  (Windows npm 全局安装)
                 3) 常见 npm 全局安装目录
    返回 None 表示未找到。
    """
    # 1) 直接查找
    for name in ("wechatsync", "wechatsync.cmd"):
        found = shutil.which(name)
        if found:
            logger.debug("wechatsync 路径: %s", found)
            return found

    # 2) 常见 npm 全局安装目录
    candidates = []
    # Windows
    if os.name == "nt":
        import pathlib
        home = pathlib.Path.home()
        candidates.extend([
            os.environ.get("APPDATA", "") + r"\npm\wechatsync.cmd",
            str(home / "AppData" / "Roaming" / "npm" / "wechatsync.cmd"),
        ])
    # Unix
    candidates.extend([
        "/usr/local/bin/wechatsync",
        "/usr/bin/wechatsync",
        os.path.expanduser("~/.npm-global/bin/wechatsync"),
        os.path.expanduser("~/.local/bin/wechatsync"),
    ])

    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            logger.debug("wechatsync 路径(候选): %s", candidate)
            return candidate

    return None


def sync_to_platforms(
    md_path,
    platforms,
    title=None,
    cover_path=None,
    timeout=None,
    allow_unknown_platforms=False,
):
    """
    调用 wechatsync CLI 同步 markdown 到指定平台。

    Args:
        md_path: markdown 文件路径
        platforms: list[str],平台名列表
        title: 可选,文章标题;留空让 wechatsync 从 markdown 首个 # 提取
        cover_path: 可选,封面图本地路径(部分平台需要)
        timeout: 子进程超时秒数。None 时用 compute_default_timeout(platforms)
                 (公式: 60 + 60 * n, clamp 到 [120, 900])
        allow_unknown_platforms: True 时未知平台只 warn 并透传;
                                 False(默认)时抛 ValueError 硬失败。

    Returns:
        dict: {
            "success": bool,            # 是否全部平台都成功
            "platforms": list[str],     # 传入的平台
            "stdout": str,              # CLI 原始 stdout
            "stderr": str,              # CLI 原始 stderr
            "returncode": int,          # CLI 退出码
            "parsed": dict|None,        # 如果 CLI 输出 JSON 则解析,否则 None
        }
    """
    md_path = Path(md_path)
    if not md_path.exists():
        raise FileNotFoundError(f"文章文件不存在: {md_path}")

    invalid = [p for p in platforms if p not in SUPPORTED_PLATFORMS]
    if invalid:
        if allow_unknown_platforms:
            logger.warning("以下平台不在已知列表中: %s", invalid)
        else:
            raise ValueError(
                f"未知平台: {invalid}。已知平台: {sorted(SUPPORTED_PLATFORMS)}。"
                f"如确需透传,请使用 --allow-unknown-platforms。"
            )

    if timeout is None:
        timeout = compute_default_timeout(platforms)

    wechatsync_bin = _find_wechatsync()
    if not wechatsync_bin:
        wechatsync_bin = "wechatsync"  # 兜底, 让 subprocess 报 FileNotFoundError

    cmd = [
        wechatsync_bin, "sync",
        str(md_path),
        "-p", ",".join(platforms),
    ]
    if title:
        cmd.extend(["--title", title])
    if cover_path:
        cmd.extend(["--cover", str(cover_path)])

    logger.info("执行: %s  超时: %ds (平台数=%d)", ' '.join(cmd), timeout, len(platforms))

    # 确保 config.yaml 中的 token 已注入到环境变量（供 wechatsync CLI 使用）
    if load_env:
        load_env()

    # 设置 UTF-8 编码环境，避免 Windows GBK 解码错误
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as e:
        # 超时后从 e.stdout 拿部分输出,帮助定位"哪几个平台已经成功"
        partial_stdout = e.stdout or ""
        if isinstance(partial_stdout, bytes):
            partial_stdout = partial_stdout.decode("utf-8", errors="replace")
        partial_stderr = e.stderr or ""
        if isinstance(partial_stderr, bytes):
            partial_stderr = partial_stderr.decode("utf-8", errors="replace")
        tail = partial_stdout[-500:] if partial_stdout else ""
        if tail:
            logger.error("wechatsync 同步超时 (%ds, 平台: %s), 最后输出: %s", timeout, ",".join(platforms), tail[:200])
        else:
            logger.error("wechatsync 同步超时 (%ds, 平台: %s), 未采集到 stdout", timeout, ",".join(platforms))
        return {
            "success": False,
            "platforms": platforms,
            "stdout": partial_stdout,
            "stderr": f"同步超时({timeout}s): {e}\n{partial_stderr}",
            "returncode": -1,
            "parsed": None,
        }
    except FileNotFoundError as e:
        logger.warning(
            "wechatsync CLI 未安装,跳过同步 —— 命令: %s —— 错误: %s —— 请确保已安装 wechatsync (npm i -g wechatsync) 且可执行文件在 PATH 中",
            ' '.join(cmd), e,
        )
        return {
            "success": False,
            "platforms": platforms,
            "stdout": "",
            "stderr": (
                f"wechatsync CLI 未安装或不在 PATH 中\n"
                f"尝试执行的命令: {' '.join(cmd)}\n"
                f"系统错误: {e}\n"
                f"请安装: npm i -g wechatsync, 并确保安装路径在系统 PATH 环境变量中"
            ),
            "returncode": -1,
            "parsed": None,
        }

    parsed = None
    if proc.stdout:
        try:
            parsed = json.loads(proc.stdout)
        except json.JSONDecodeError:
            pass

    # 判断是否真正成功：wechatsync 即使同步失败也可能 returncode=0
    stderr_text = proc.stderr or ""
    stdout_text = proc.stdout or ""
    sync_failed = any(
        keyword in stderr_text or keyword in stdout_text
        for keyword in ("同步失败", "Invalid or missing token", "✖", "✘", "✗")
    )
    success = proc.returncode == 0 and not sync_failed

    return {
        "success": success,
        "platforms": platforms,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "returncode": proc.returncode,
        "parsed": parsed,
    }


def run(
    md_path,
    platforms,
    title=None,
    cover_path=None,
    strict=False,
    timeout=None,
    allow_unknown_platforms=False,
):
    """
    主入口:做环境检查 + 警告本地图片 + 调 CLI。

    Args:
        strict: True 时环境不达标直接 raise;False 时只 warn 并返回失败结果
                (集成到 publish.py 时用 False,避免打断微信发布的成功结果)
        timeout: 子进程超时秒数。None 时按平台数量自动推算。
        allow_unknown_platforms: 透传给 sync_to_platforms。False(默认)下遇到
                未知平台会 raise ValueError,被这里捕获后归一成失败结果返回。
    """
    logger.info("多平台同步: %s", ', '.join(platforms))

    logger.info("[检查 1/2] 前置环境...")
    ok, problems = check_prerequisites(verbose=True)
    if not ok:
        for p in problems:
            logger.warning("  %s", p)
        if strict:
            raise RuntimeError("wechatsync 环境检查未通过")
        return {
            "success": False,
            "platforms": platforms,
            "stdout": "",
            "stderr": "\n".join(problems),
            "returncode": -1,
            "parsed": None,
        }

    # 图片路径提醒
    logger.info("[检查 2/2] 图片路径...")
    md_content = Path(md_path).read_text(encoding="utf-8")
    local_imgs, remote_imgs = scan_local_images(md_content)
    logger.info("远程 URL 图片: %d 张 (wechatsync 会自动转存)", len(remote_imgs))
    if local_imgs:
        logger.warning("本地路径图片: %d 张, wechatsync 可能不支持", len(local_imgs))
        for p in local_imgs[:3]:
            logger.warning("  %s", p)
        if len(local_imgs) > 3:
            logger.warning("  ...还有 %d 张", len(local_imgs) - 3)

    # 调 CLI
    logger.info("[同步] 调用 wechatsync CLI...")
    try:
        result = sync_to_platforms(
            md_path,
            platforms,
            title=title,
            cover_path=cover_path,
            timeout=timeout,
            allow_unknown_platforms=allow_unknown_platforms,
        )
    except ValueError as e:
        # 未知平台硬失败,归一成结果 dict 便于 publish.py 继续收尾
        logger.error("未知平台: %s", e)
        if strict:
            raise
        return {
            "success": False,
            "platforms": platforms,
            "stdout": "",
            "stderr": str(e),
            "returncode": -1,
            "parsed": None,
        }

    if result["success"]:
        logger.info("同步完成 (各平台已保存为草稿)")
    else:
        stderr_info = result["stderr"][:200] if result["stderr"] else ""
        logger.warning("同步未全部成功 (returncode=%d, stderr=%s)", result["returncode"], stderr_info)

    return result


def parse_platforms(raw):
    """把 'zhihu,juejin, csdn' 规范化成 ['zhihu','juejin','csdn']。"""
    return [p.strip() for p in raw.split(",") if p.strip()]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="多平台同步发布(基于 wechatsync CLI)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 同步到知乎 + 掘金
  python multi_publish.py --input article.md --platforms zhihu,juejin

  # 指定标题和封面
  python multi_publish.py -i article.md -p csdn --title "自定义标题" --cover cover.jpg

  # 只做环境检查
  python multi_publish.py --check
        """,
    )
    parser.add_argument("--input", "-i", help="Markdown 文件路径")
    parser.add_argument(
        "--platforms", "-p",
        help=f"目标平台,逗号分隔。已知: {','.join(sorted(SUPPORTED_PLATFORMS))}",
    )
    parser.add_argument("--title", "-t", help="文章标题(默认从 markdown 首个 # 提取)")
    parser.add_argument("--cover", "-c", help="封面图本地路径(部分平台需要)")
    parser.add_argument(
        "--check", action="store_true",
        help="仅做环境前置检查,不发布",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="环境不达标直接报错退出(默认只 warn)",
    )
    parser.add_argument(
        "--allow-unknown-platforms", action="store_true",
        help="允许传入不在已知列表中的平台(默认直接报错退出)",
    )
    parser.add_argument(
        "--timeout", type=int, default=None,
        help="同步子进程超时秒数(默认按平台数自动: 60+60*n, clamp 到 [120, 900])",
    )

    args = parser.parse_args()

    if args.check:
        ok, problems = check_prerequisites(verbose=True)
        if ok:
            print("\n✓ 所有前置检查通过")
            sys.exit(0)
        else:
            print("\n✗ 前置检查未通过:")
            for p in problems:
                print(f"  - {p}")
            sys.exit(1)

    if not args.input or not args.platforms:
        parser.error("请提供 --input 和 --platforms 参数(或用 --check 只做检查)")

    platforms = parse_platforms(args.platforms)
    if not platforms:
        parser.error("--platforms 不能为空")

    result = run(
        md_path=args.input,
        platforms=platforms,
        title=args.title,
        cover_path=args.cover,
        strict=args.strict,
        timeout=args.timeout,
        allow_unknown_platforms=args.allow_unknown_platforms,
    )

    # 独立运行时:失败返回非 0 退出码方便 shell 捕获
    sys.exit(0 if result["success"] else 1)
