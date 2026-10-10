"""One-way Skill synchronization from an audited repository checkout; stdlib only."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
NAME = "virtual-perturbation-toolkit"
MANIFEST = "sync_manifest.json"
TESTED = {"numpy": "2.4.6", "pandas": "3.0.6", "scipy": "1.15.3", "tensorly": "0.9.0",
          "scikit-learn": "1.9.1", "anndata": "0.13.4", "h5py": "3.16.0"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def version(root):
    return (root / "VERSION").read_text(encoding="utf-8").strip()


def default_skill_dir():
    codex = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    return codex / "skills" / NAME


def bundle(root):
    sources = {"SKILL.md": root / "SKILL.md", "scripts/run_toolkit.py": root / "scripts/run_toolkit.py",
               "agents/openai.yaml": root / "agents/openai.yaml"}
    data = {name: path.read_bytes() for name, path in sources.items()}
    data["scripts/toolkit_path.json"] = (json.dumps({"toolkit_path": str(root.resolve()),
        "toolkit_version": version(root)}, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return data


def inspect_install(root, target):
    wanted = {name: digest(data) for name, data in bundle(root).items()}
    manifest_path = target / MANIFEST
    if not target.exists():
        return {"state": "NOT_INSTALLED", "installed_version": None, "modified_files": [],
                "update_available": True, "repository_version": version(root)}
    if not manifest_path.is_file():
        return {"state": "UNTRACKED_INSTALL", "installed_version": None,
                "modified_files": [p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()],
                "update_available": True, "repository_version": version(root)}
    manifest = read_json(manifest_path)
    modified = [name for name, expected in manifest["files"].items()
                if not (target / name).is_file() or digest((target / name).read_bytes()) != expected]
    # A newly managed file must not overwrite an existing, untracked user file.
    modified += [name for name in wanted if name not in manifest["files"] and (target / name).exists()]
    return {"state": "MODIFIED" if modified else "CLEAN", "installed_version": manifest["version"],
            "repository_version": version(root), "modified_files": sorted(set(modified)),
            "update_available": manifest["files"] != wanted or manifest["version"] != version(root)}


def sync(root, target, backup=None):
    if target.resolve() == root.resolve() or target.resolve() in root.resolve().parents:
        raise ValueError("Skill 目标不能是源码仓库本身或其上级目录。")
    data = bundle(root)
    status = inspect_install(root, target)
    backup_path = None
    if status["state"] in ["MODIFIED", "UNTRACKED_INSTALL"]:
        if backup is None:
            raise ValueError("检测到手动修改或未跟踪的旧 Skill；拒绝覆盖。指定 --backup <目录> 先完整备份。")
        backup = Path(backup).resolve()
        target_abs = target.resolve()
        if backup == target_abs or target_abs in backup.parents:
            raise ValueError("备份目录不能位于被更新的 Skill 内。")
        stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S%f")
        backup_path = backup / f"{NAME}-{stamp}"
        shutil.copytree(target, backup_path)
    target.mkdir(parents=True, exist_ok=True)
    for name, content in data.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    manifest = {"version": version(root), "repository": str(root.resolve()),
                "files": {name: digest(content) for name, content in data.items()}}
    (target / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"state": "SYNCED", "skill_dir": str(target.resolve()), "version": version(root),
            "backup_path": str(backup_path) if backup_path else None, "core_code_copied": False}


def resolve(path, base):
    value = Path(path)
    return value if value.is_absolute() else (base / value).resolve()


def probe_python(executable, names, dependency_paths):
    code = ("import sys,json,importlib.metadata as m; sys.path[:0]=json.loads(sys.argv[1]); "
            "names=json.loads(sys.argv[2]); out={}; "
            "exec('for name in names:\\n try: out[name]=m.version(name)\\n except m.PackageNotFoundError: out[name]=None'); "
            "print(json.dumps({'python':sys.version,'packages':out}))")
    result = subprocess.run([str(executable), "-I", "-c", code, json.dumps(dependency_paths), json.dumps(names)],
                            capture_output=True, text=True, check=False, timeout=20)
    if result.returncode:
        raise ValueError(f"Python 依赖查询失败：{executable}; exit={result.returncode}")
    return json.loads(result.stdout)


def probe_r(executable, libraries):
    # installed.packages queries metadata without loading scientific libraries.
    code = ('.libPaths(c(commandArgs(trailingOnly=TRUE),.libPaths())); '
            'cat(R.version.string,"\\n",sep=""); p<-c("ggplot2","patchwork","ragg","jsonlite","svglite"); '
            'i<-installed.packages(); v<-i[match(p,rownames(i)),"Version"]; '
            'v[is.na(v)]<-"MISSING"; cat(paste(p,v,sep="\\t"),sep="\\n")')
    result = subprocess.run([str(executable), "--vanilla", "-e", code, *map(str, libraries)],
                            capture_output=True, text=True, check=False, timeout=20,
                            env=dict(os.environ, LC_ALL="", LC_CTYPE=""))
    if result.returncode:
        raise ValueError(f"R 依赖查询失败：{executable}; exit={result.returncode}")
    lines = result.stdout.strip().splitlines()
    return {"R": lines[0], "packages": dict(line.split("\t", 1) for line in lines[1:])}


def doctor(root, target, config_path=None):
    report = {"installation": inspect_install(root, target), "runtime_checked": False,
              "repository_missing": [name for name in ["Run.ps1", "vpt_cli.py", "scripts/run_guard.py",
                  "scripts/plot_results.R"] if not (root / name).is_file()],
              "tested_package_versions": TESTED, "scientific_validation": "NOT_ESTABLISHED"}
    errors, warnings = [], []
    if report["repository_missing"]:
        errors.append("仓库必需入口缺失")
    if report["installation"]["state"] in ["MODIFIED", "UNTRACKED_INSTALL"]:
        warnings.append("Skill 安装需要审查并备份后更新")
    if config_path:
        config_path = config_path.resolve()
        config, base = read_json(config_path), config_path.parent
        runtime, engine = config["runtime"], config["engine"]
        if engine["id"] != "dosedirko":
            errors.append(f"引擎尚未集成：{engine['id']}")
        dependencies = [str(resolve(p, base)) for p in engine.get("dependency_paths", [])]
        environments = {}
        for key, names in [("python_monitor", ["psutil"]),
                           ("python_data", ["numpy", "pandas", "scipy", "tensorly", "scikit-learn", "anndata", "h5py"])]:
            executable = resolve(runtime[key], base)
            if not executable.is_file():
                errors.append(f"运行时不存在：{key}")
                continue
            environments[key] = probe_python(executable, names, dependencies if key == "python_data" else [])
            missing = [name for name, value in environments[key]["packages"].items() if value is None]
            if config["input"]["format"] == "10x":
                missing = [name for name in missing if name not in ["anndata", "h5py"]]
            if missing:
                errors.append(f"{key} 缺依赖：{', '.join(missing)}")
            for name, tested in TESTED.items():
                actual = environments[key]["packages"].get(name)
                if actual and actual != tested:
                    warnings.append(f"{name}={actual} 与历史测试版本 {tested} 不同；需软件验收")
        report["python_environments"] = environments
        r_paths_ok = True
        for key in ["Rscript", "R_library"]:
            if not resolve(runtime[key], base).exists():
                errors.append(f"R 运行时不存在：{key}")
                r_paths_ok = False
        if r_paths_ok:
            report["R_environment"] = probe_r(resolve(runtime["Rscript"], base),
                [root / "environment/r_library", resolve(runtime["R_library"], base)])
            missing = [name for name, value in report["R_environment"]["packages"].items() if value == "MISSING"]
            if missing:
                errors.append("R 缺依赖：" + ", ".join(missing))
        source = resolve(engine["source_dir"], base) / "dosedirko"
        actual_source_names = sorted(path.name for path in source.glob("*.py"))
        if actual_source_names != sorted(engine.get("source_sha256", {})):
            errors.append("外部源码文件集合与冻结 SHA 清单不一致")
        report["engine_source_matches"] = {}
        for name, expected in engine.get("source_sha256", {}).items():
            path = source / name
            matches = path.is_file() and digest(path.read_bytes()) == expected
            report["engine_source_matches"][name] = matches
            if not matches:
                errors.append(f"外部源码缺失或 SHA 不一致：{name}")
        if not engine.get("source_sha256"):
            errors.append("未提供外部核心源码冻结 SHA")
        report["runtime_checked"] = True
    report.update(state="BLOCKED" if errors else "READY_FOR_PREFLIGHT" if config_path else "INSTALLATION_ONLY",
                  errors=errors, warnings=warnings,
                  scope="只查询版本、路径和哈希；不导入数值算法、不训练、不改系统；实际资源检查仍由 Run.ps1 执行")
    return report


def main():
    parser = argparse.ArgumentParser(description="从仓库单向同步薄 Skill；不自动 git pull 或安装依赖。")
    parser.add_argument("command", choices=["install", "update", "status", "check-update", "doctor", "version"])
    parser.add_argument("--skill-dir", type=Path, default=default_skill_dir())
    parser.add_argument("--backup", type=Path, help="存在手改或旧安装时，先备份到此目录再更新")
    parser.add_argument("--config", type=Path, help="doctor 检查的本地任务配置")
    args = parser.parse_args()
    try:
        if args.command in ["install", "update"]:
            result = sync(ROOT, args.skill_dir, args.backup)
        elif args.command == "doctor":
            result = doctor(ROOT, args.skill_dir, args.config)
        else:
            result = inspect_install(ROOT, args.skill_dir)
            if args.command == "version":
                result = {key: result[key] for key in ["repository_version", "installed_version", "state"]}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if result.get("state") == "BLOCKED" else 0
    except (ValueError, OSError, KeyError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        print(json.dumps({"state": "BLOCKED", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
