"""Standard-library launcher; numerical code remains in the repository."""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def locate_toolkit():
    script = Path(__file__).resolve()
    candidate = script.parents[1]
    if (candidate / "Run.ps1").is_file():
        return candidate
    mapping = script.with_name("toolkit_path.json")
    if not mapping.is_file():
        raise ValueError("Skill 尚未安装路径映射；从仓库执行 scripts/skill_sync.py install。")
    toolkit = Path(json.loads(mapping.read_text(encoding="utf-8-sig"))["toolkit_path"])
    if not (toolkit / "Run.ps1").is_file():
        raise ValueError(f"仓库入口不存在：{toolkit}; 更新 Skill 路径映射。")
    return toolkit


def build_command(toolkit, config, output=None):
    config = Path(config).resolve()
    if not config.is_file():
        raise ValueError(f"配置文件不存在：{config}")
    command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
               str(toolkit / "Run.ps1"), "-Config", str(config)]
    if output:
        command.extend(["-OutputDir", str(Path(output).resolve())])
    return command


def main():
    parser = argparse.ArgumentParser(description="配置驱动的本地虚拟干扰入口；不复制外部算法。")
    parser.add_argument("--config", help="已审查的任务 JSON 配置")
    parser.add_argument("--output", help="新的输出目录")
    parser.add_argument("--locate", action="store_true", help="显示当前仓库路径")
    parser.add_argument("--version", action="store_true", help="显示仓库及 Skill 安装版本")
    parser.add_argument("--doctor", action="store_true", help="检查安装；配合 --config 检查指定运行环境")
    args = parser.parse_args()
    try:
        toolkit = locate_toolkit()
        if sum([args.locate, args.version, args.doctor]) > 1:
            parser.error("--locate、--version、--doctor 每次选择一个。")
        if args.locate:
            print(toolkit)
            return 0
        if args.version or args.doctor:
            command = [sys.executable, "-B", "-X", "utf8", str(toolkit / "scripts/skill_sync.py"),
                       "version" if args.version else "doctor"]
            skill = Path(__file__).resolve().parents[1]
            if skill != toolkit:
                command.extend(["--skill-dir", str(skill)])
            if args.doctor and args.config:
                command.extend(["--config", str(Path(args.config).resolve())])
        else:
            if not args.config:
                parser.error("运行必须提供 --config；也可使用 --locate、--version 或 --doctor。")
            command = build_command(toolkit, args.config, args.output)
        return subprocess.run(command, cwd=str(toolkit), check=False).returncode
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as error:
        print(f"BLOCKED: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
