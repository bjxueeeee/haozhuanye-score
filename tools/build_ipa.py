#!/usr/bin/env python3
"""Build an unsigned device IPA from an Xcode or existing Capacitor iOS project."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import uuid
import zipfile


class BuildError(RuntimeError):
    pass


class Runner:
    def __init__(self, root: Path, log: Path | None, dry_run: bool = False):
        self.root, self.log, self.dry_run = root, log, dry_run

    def write(self, text: str):
        print(text, flush=True)
        if self.log:
            with self.log.open("a", encoding="utf-8") as handle:
                handle.write(text + "\n")

    def run(self, command: list[str], capture: bool = False) -> str:
        # Lists are passed directly to subprocess: paths/spaces are not shell commands.
        self.write("$ " + subprocess.list2cmdline(command))
        if self.dry_run:
            return ""
        try:
            if capture:
                result = subprocess.run(
                    command, cwd=self.root, capture_output=True, text=True,
                    encoding="utf-8", errors="replace", check=False,
                )
                if result.stdout:
                    self.write(result.stdout.rstrip())
                if result.stderr:
                    self.write(result.stderr.rstrip())
                if result.returncode:
                    raise BuildError(f"命令失败（退出码 {result.returncode}）：{command[0]}")
                return result.stdout
            process = subprocess.Popen(
                command, cwd=self.root, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
            )
            assert process.stdout is not None
            for line in process.stdout:
                self.write(line.rstrip("\r\n"))
            if process.wait():
                raise BuildError(f"命令失败（退出码 {process.returncode}）：{command[0]}")
            return ""
        except FileNotFoundError as exc:
            raise BuildError(f"找不到命令：{command[0]}") from exc


def resolve_from(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return (path if path.is_absolute() else root / path).resolve()


def find_project(root: Path, explicit: str | None) -> Path:
    if explicit:
        path = resolve_from(root, explicit)
        if not path.is_dir() or path.suffix not in (".xcodeproj", ".xcworkspace"):
            raise BuildError(f"工程必须是存在的 .xcodeproj 或 .xcworkspace 目录：{path}")
        return path
    # Prefer conventional top-level locations. Do not walk dependencies or project internals.
    search_roots = [root, root / "ios", root / "ios" / "App"]
    candidates = sorted({
        item.resolve() for directory in search_roots if directory.is_dir()
        for item in directory.iterdir()
        if item.is_dir() and item.suffix in (".xcodeproj", ".xcworkspace")
        and item.stem not in ("Pods", "Package")
    })
    # A CocoaPods workspace takes precedence over its same-named project.
    workspaces = {(p.parent, p.stem) for p in candidates if p.suffix == ".xcworkspace"}
    candidates = [p for p in candidates if p.suffix == ".xcworkspace"
                  or (p.parent, p.stem) not in workspaces]
    if len(candidates) != 1:
        choices = "\n".join(f"  {p}" for p in candidates) or "  未发现工程"
        raise BuildError("无法唯一确定工程；请用 --project 指定：\n" + choices)
    return candidates[0]


def choose_scheme(output: str) -> str:
    try:
        info = json.loads(output)
        section = info.get("workspace") or info.get("project") or {}
        schemes = section.get("schemes", [])
    except (ValueError, AttributeError) as exc:
        raise BuildError("无法解析 Xcode scheme 列表，请用 --scheme 明确指定。") from exc
    if len(schemes) != 1:
        raise BuildError("存在多个或没有 scheme；请用 --scheme 指定：" + ", ".join(schemes))
    return schemes[0]


def safe_component(value: str) -> str:
    text = re.sub(r"[^\w.-]+", "-", str(value), flags=re.UNICODE).strip(".-")
    if not text:
        raise BuildError("应用名称或版本无法组成有效文件名。")
    return text


def inspect_app(archive: Path, app_name: str | None) -> tuple[Path, dict]:
    applications = archive / "Products" / "Applications"
    apps = sorted(applications.glob("*.app"))
    if app_name:
        apps = [p for p in apps if p.name == app_name]
    if len(apps) != 1:
        raise BuildError("Archive 中未找到唯一主应用；多应用时用 --app 指定完整名称（如 App.app）。")
    app = apps[0]
    try:
        with (app / "Info.plist").open("rb") as handle:
            info = plistlib.load(handle)
    except (OSError, ValueError, plistlib.InvalidFileException) as exc:
        raise BuildError(f"无法读取应用 Info.plist：{app}") from exc
    platforms = info.get("CFBundleSupportedPlatforms", [])
    platform_name = info.get("DTPlatformName")
    if (platforms and "iPhoneOS" not in platforms) or (platform_name and platform_name != "iphoneos"):
        raise BuildError("产物不是 iPhoneOS 真机应用，拒绝打包模拟器或其他平台产物。")
    if "iPhoneOS" not in platforms and platform_name != "iphoneos":
        raise BuildError("Info.plist 缺少 iPhoneOS 真机平台标识。")
    executable = info.get("CFBundleExecutable", "")
    if (not executable or executable in (".", "..") or "/" in executable
            or "\\" in executable or not (app / executable).is_file()):
        raise BuildError("应用主可执行文件无效或不存在。")
    if not info.get("CFBundleIdentifier"):
        raise BuildError("应用缺少 CFBundleIdentifier。")
    return app, info


def verify_zip(path: Path, bundle_name: str):
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            raise BuildError(f"IPA ZIP 校验失败：{bad}")
        if f"Payload/{bundle_name}/Info.plist" not in archive.namelist():
            raise BuildError("IPA 内缺少 Payload/<应用>.app/Info.plist。")


def publish_ipa(source: Path, destination: Path, overwrite: bool):
    # Exclusive creation protects earlier builds unless overwrite was explicitly requested.
    with source.open("rb") as src, destination.open("wb" if overwrite else "xb") as dst:
        shutil.copyfileobj(src, dst)
    digest = hashlib.file_digest if hasattr(hashlib, "file_digest") else None
    with destination.open("rb") as handle:
        if digest:
            value = digest(handle, "sha256").hexdigest()
        else:
            hasher = hashlib.sha256()
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
            value = hasher.hexdigest()
    destination.with_suffix(destination.suffix + ".sha256").write_text(
        f"{value}  {destination.name}\n", encoding="utf-8",
    )


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", default=".", help="仓库根目录，默认当前目录")
    p.add_argument("--project", help="相对 root 或绝对路径：.xcodeproj / .xcworkspace")
    p.add_argument("--scheme", help="Xcode shared scheme；仅有一个时自动选择")
    p.add_argument("--configuration", default="Release")
    p.add_argument("--output", default="ipa-output", help="输出目录，相对 root 或绝对路径")
    p.add_argument("--name", help="IPA 文件名前缀，默认应用 Bundle 名称")
    p.add_argument("--app", help="多个主应用时指定 archive 中的完整名称，如 App.app")
    p.add_argument("--capacitor", action="store_true", help="先 npm ci、npm run <web-script>、cap sync ios")
    p.add_argument("--web-script", default="build", help="Capacitor 前端构建 npm script")
    p.add_argument("--overwrite", action="store_true", help="允许覆盖同名 IPA")
    p.add_argument("--dry-run", action="store_true", help="仅打印准备/归档命令，不写文件、不执行、不下载")
    return p


def build(args: argparse.Namespace) -> Path | None:
    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        raise BuildError(f"仓库目录不存在：{root}")
    if not args.dry_run and sys.platform != "darwin":
        raise BuildError("真机编译需要 macOS + Xcode。Windows 请使用附带的 GitHub Actions 模板；--dry-run 可预览。")
    output = resolve_from(root, args.output)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    work = output / "builds" / ("preview" if args.dry_run else run_id)
    if not args.dry_run:
        work.mkdir(parents=True, exist_ok=False)
    runner = Runner(root, None if args.dry_run else work / "build.log", args.dry_run)
    runner.write(f"工作目录：{work}")
    if args.capacitor:
        if not (root / "package-lock.json").is_file():
            raise BuildError("--capacitor 需要 package-lock.json；其他包管理器请自行安装和构建后去掉此参数。")
        runner.run(["npm", "ci"])
        runner.run(["npm", "run", args.web_script])
        cap = root / "node_modules" / ".bin" / "cap"
        runner.run([str(cap), "sync", "ios"])
    project = find_project(root, args.project)
    selector = ["-workspace" if project.suffix == ".xcworkspace" else "-project", str(project)]
    scheme = args.scheme
    if not scheme:
        if args.dry_run:
            scheme = "<请用 --scheme 指定>"
        else:
            scheme = choose_scheme(runner.run(["xcodebuild", *selector, "-list", "-json"], capture=True))
    archive = work / "App.xcarchive"
    runner.run([
        "xcodebuild", *selector, "-scheme", scheme, "-configuration", args.configuration,
        "-destination", "generic/platform=iOS", "-archivePath", str(archive),
        "-derivedDataPath", str(work / "DerivedData"), "CODE_SIGNING_ALLOWED=NO",
        "CODE_SIGNING_REQUIRED=NO", "CODE_SIGN_IDENTITY=", "archive",
    ])
    if args.dry_run:
        runner.write("预览结束；实际运行还会检查真机 arm64、打包 Payload 并生成 SHA-256。")
        return None
    app, info = inspect_app(archive, args.app)
    architectures = runner.run(["xcrun", "lipo", "-archs", str(app / info["CFBundleExecutable"])], capture=True)
    if "arm64" not in architectures.split():
        raise BuildError("主程序没有 arm64 架构，拒绝生成 iPhone IPA。")
    name = safe_component(args.name or info.get("CFBundleName") or app.stem)
    version = safe_component(info.get("CFBundleShortVersionString") or "unknown")
    destination = output / f"{name}-{version}-unsigned.ipa"
    if not args.overwrite and (destination.exists() or destination.with_suffix(".ipa.sha256").exists()):
        raise BuildError(f"产物或校验文件已存在；用 --overwrite 覆盖，或更换 --output：{destination}")
    payload = work / "staging" / "Payload"
    payload.mkdir(parents=True)
    # ditto preserves the Apple bundle's metadata and symbolic links.
    runner.run(["ditto", str(app), str(payload / app.name)])
    temporary_ipa = work / "app.ipa"
    runner.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(payload), str(temporary_ipa)])
    verify_zip(temporary_ipa, app.name)
    publish_ipa(temporary_ipa, destination, args.overwrite)
    runner.write(f"完成：{destination}")
    runner.write("此 IPA 未签名；安装到 iPhone 前需使用有效签名重新签名。")
    return destination


def main() -> int:
    try:
        build(parser().parse_args())
        return 0
    except (BuildError, OSError, zipfile.BadZipFile) as exc:
        print(f"构建失败：{exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("构建已中断。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
