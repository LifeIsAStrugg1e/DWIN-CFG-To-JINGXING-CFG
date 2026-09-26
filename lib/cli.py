#!/usr/bin/env python3
"""独立转换核心的命令行入口。"""

import argparse
from pathlib import Path

try:
    from .converter import (
        ConfigError, convert_to_jgxing, generate_config_txt,
        parse_dwin_config, resolve_system,
    )
except ImportError:
    from converter import (
        ConfigError, convert_to_jgxing, generate_config_txt,
        parse_dwin_config, resolve_system,
    )


SYSTEMS = ("AUTO", "JGUS", "JGUSII", "INSTRUCTION")
SOURCE_MODELS = ("AUTO", "T5L_DGUSII", "T5L_TA")


def convert_file(input_path: Path, output_path: Path, requested_system: str,
                 source_model: str = "AUTO") -> None:
    model_hint = None if source_model == "AUTO" else source_model
    dwin = parse_dwin_config(input_path.read_bytes(), model_hint=model_hint)
    system = resolve_system(dwin.model, requested_system)
    result = convert_to_jgxing(dwin, system)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(generate_config_txt(result, system), encoding="utf-8")
    print(f"{input_path} -> {output_path} [{dwin.model_name}, {system}]")


def main() -> int:
    parser = argparse.ArgumentParser(description="迪文 CFG 转晶兴 CONFIG.txt")
    parser.add_argument("input", type=Path, help="输入 CFG 文件或包含 CFG 的目录")
    parser.add_argument("output", type=Path, help="输出文件或目录")
    parser.add_argument(
        "-s", "--system", choices=SYSTEMS, default="AUTO",
        help="目标系统；AUTO 根据检测到的型号选择（默认：AUTO）",
    )
    parser.add_argument(
        "--source-model", choices=SOURCE_MODELS, default="AUTO",
        help="T5LC1 的源型号；该文件头无法自动区分 DGUSII 与 TA",
    )
    args = parser.parse_args()

    try:
        if args.input.is_file():
            convert_file(args.input, args.output, args.system, args.source_model)
            return 0

        if args.input.is_dir():
            files = sorted({*args.input.glob("*.CFG"), *args.input.glob("*.cfg")})
            if not files:
                parser.error(f"目录中没有 CFG 文件：{args.input}")
            for source in files:
                convert_file(
                    source, args.output / f"{source.stem}_CONFIG.txt",
                    args.system, args.source_model,
                )
            return 0
    except (ConfigError, OSError) as error:
        parser.error(str(error))

    parser.error(f"输入路径不存在：{args.input}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
