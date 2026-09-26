"""Command-line and compatibility API for DWIN CFG conversion."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence, Union

from lib import (
    ConfigError,
    convert_to_jgxing,
    generate_config_txt,
    parse_dwin_config,
    resolve_system,
)


PathLike = Union[str, Path]
OUTPUT_NAME = "config.TXT"
SYSTEMS = ("AUTO", "JGUS", "JGUSII", "INSTRUCTION")
SOURCE_MODELS = ("T5L_DGUSII", "T5L_TA")

# Compatibility name used by the first Python implementation.
CfgConvertError = ConfigError


def generate_config_text(
    data: bytes,
    source_model: Optional[str] = None,
    system: str = "AUTO",
) -> str:
    """Parse source bytes and generate target register configuration text."""
    dwin = parse_dwin_config(data, model_hint=source_model)
    target_system = resolve_system(dwin.model, system)
    return generate_config_txt(convert_to_jgxing(dwin, target_system), target_system)


def convert_cfg(
    input_path: PathLike,
    output_path: Optional[PathLike] = None,
    source_model: Optional[str] = None,
    system: str = "AUTO",
) -> Path:
    """Convert one CFG file and return the generated output path."""
    source = Path(input_path)
    target = Path(output_path) if output_path is not None else source.with_name(OUTPUT_NAME)
    text = generate_config_text(source.read_bytes(), source_model, system)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as output:
        output.write(text)
    return target


cfg_convert_to_file = convert_cfg


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="将迪文 CFG 转换为晶兴寄存器配置")
    parser.add_argument("input", type=Path, help="输入 CFG 文件")
    parser.add_argument("-o", "--output", type=Path, help="输出文件，默认同目录 config.TXT")
    parser.add_argument(
        "-s", "--system", choices=SYSTEMS, default="AUTO",
        help="目标系统，默认按源型号选择",
    )
    parser.add_argument(
        "--source-model", choices=SOURCE_MODELS,
        help="T5LC1 必填：选择 T5L_DGUSII 或 T5L_TA",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        output = convert_cfg(args.input, args.output, args.source_model, args.system)
    except (ConfigError, OSError) as error:
        print("转换失败：{}".format(error))
        return 1
    print("转换成功：{}".format(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
