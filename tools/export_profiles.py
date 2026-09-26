"""Validate profiles/设备规则.xlsx and export deterministic runtime JSON."""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET


NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
DOC_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
HEX_RE = re.compile(r"^[0-9A-Fa-f]+$")
VALID_SYSTEMS = {"JGUS", "JGUSII", "INSTRUCTION"}
VALID_FIELD_TYPES = {"bit", "bitfield", "uint", "divisor", "direct_baud", "constant"}
VALID_OPERATIONS = {"truthy", "falsy", "equals", "not_equals"}
VALID_POLICIES = {"always", "if_present", "if_nonzero"}
VALID_TRANSFORMS = {
    "direct", "enum", "percent_to_63", "seconds", "seconds_x2",
    "touch_type", "debug_switch",
}
VALID_REGISTERS = {"R1", "R2", "R3", "RA", "RB", "RC", "R6", "R7", "R8", "R10", "R11", "R12", "RD", "RE"}
VALID_SOURCE_FIELDS = {
    "baudrate", "direction", "crc_enable", "buzzer_enable", "tp_auto_upload",
    "tp_buzzer", "backlight_standby", "load_22", "var_per_page",
    "brightness_on", "brightness_off", "backlight_time", "bg_image_id",
    "audio_id", "tp_type", "debug_enable", "tp_switch_enable",
}


class ExportError(ValueError):
    pass


def _column_index(reference: str) -> int:
    letters = "".join(character for character in reference if character.isalpha())
    result = 0
    for character in letters:
        result = result * 26 + ord(character.upper()) - ord("A") + 1
    return result - 1


def _read_workbook(path: Path) -> Dict[str, List[List[Any]]]:
    with zipfile.ZipFile(str(path)) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("m:si", NS):
                shared.append("".join(node.text or "" for node in item.iterfind(".//m:t", NS)))

        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_targets = {item.attrib["Id"]: item.attrib["Target"] for item in relationships.findall("r:Relationship", REL_NS)}
        sheets = {}
        for sheet in workbook.findall("m:sheets/m:sheet", NS):
            name = sheet.attrib["name"]
            rel_id = sheet.attrib["{{{}}}id".format(DOC_REL)]
            target = rel_targets[rel_id].lstrip("/")
            if not target.startswith("xl/"):
                target = "xl/" + target
            root = ET.fromstring(archive.read(target))
            rows = []
            for row in root.findall("m:sheetData/m:row", NS):
                values = []
                for cell in row.findall("m:c", NS):
                    index = _column_index(cell.attrib["r"])
                    while len(values) <= index:
                        values.append(None)
                    cell_type = cell.attrib.get("t")
                    value_node = cell.find("m:v", NS)
                    if cell_type == "inlineStr":
                        inline = cell.find("m:is", NS)
                        value = "".join(node.text or "" for node in inline.iterfind(".//m:t", NS)) if inline is not None else ""
                    elif value_node is None:
                        value = None
                    elif cell_type == "s":
                        value = shared[int(value_node.text)]
                    elif cell_type == "b":
                        value = value_node.text == "1"
                    elif cell_type == "str":
                        value = value_node.text or ""
                    else:
                        number = float(value_node.text)
                        value = int(number) if number.is_integer() else number
                    values[index] = value
                rows.append(values)
            sheets[name] = rows
    return sheets


def _records(rows: List[List[Any]], first_header: str) -> List[Dict[str, Any]]:
    header_index = next((index for index, row in enumerate(rows) if row and row[0] == first_header), None)
    if header_index is None:
        raise ExportError("找不到表头：{}".format(first_header))
    headers = rows[header_index]
    result = []
    for row_number, row in enumerate(rows[header_index + 1 :], header_index + 2):
        if not any(value not in (None, "") for value in row):
            continue
        record = {header: (row[index] if index < len(row) else None) for index, header in enumerate(headers) if header}
        record["_row"] = row_number
        result.append(record)
    return result


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _integer(value: Any, label: str, allow_blank: bool = False) -> Optional[int]:
    if value in (None, "") and allow_blank:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ExportError("{} 必须是整数，实际为 {!r}".format(label, value))


def _hex(value: Any, label: str, allow_blank: bool = False) -> Optional[int]:
    text = _text(value).replace("0x", "").replace("0X", "")
    if not text and allow_blank:
        return None
    if not text or not HEX_RE.match(text):
        raise ExportError("{} 必须是十六进制文本，实际为 {!r}".format(label, value))
    return int(text, 16)


def _hex_list(value: Any, label: str) -> List[int]:
    text = _text(value)
    if not text:
        return []
    return [_hex(item.strip(), label) for item in text.split(",")]


def _boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "是"}


def export_profiles(workbook_path: Path, output_dir: Path) -> None:
    sheets = _read_workbook(workbook_path)
    required_sheets = {"设备型号", "源字段", "位映射", "寄存器默认值", "枚举映射"}
    missing = required_sheets - set(sheets)
    if missing:
        raise ExportError("工作簿缺少工作表：{}".format(", ".join(sorted(missing))))

    device_rows = _records(sheets["设备型号"], "DeviceID")
    field_rows = _records(sheets["源字段"], "DeviceID")
    bit_rows = _records(sheets["位映射"], "TargetSystem")
    register_rows = _records(sheets["寄存器默认值"], "TargetSystem")
    enum_rows = _records(sheets["枚举映射"], "MapName")

    mapped_source_fields = {
        _text(row.get("SourceField"))
        for row in bit_rows
        if _text(row.get("TargetRegister")) or row.get("TargetBit") not in (None, "")
    }

    devices = {}
    headers = {}
    for row in device_rows:
        model = _text(row.get("DeviceID"))
        if not model:
            raise ExportError("设备型号第 {} 行缺少 DeviceID".format(row["_row"]))
        if model in devices:
            raise ExportError("DeviceID 重复：{}".format(model))
        if _text(row.get("Status")) != "已验证":
            continue
        header = _text(row.get("HeaderHex")).replace(" ", "").upper()
        if len(header) % 2 or not HEX_RE.match(header):
            raise ExportError("{} 的 HeaderHex 无效".format(model))
        headers.setdefault(header, model)
        system = _text(row.get("DefaultSystem"))
        if system not in VALID_SYSTEMS:
            raise ExportError("{} 的默认目标系统无效：{}".format(model, system))
        devices[model] = {
            "model": model,
            "display_name": _text(row.get("DisplayName")) or model,
            "header_hex": header,
            "minimum_size": _integer(row.get("MinimumSize"), "{}.MinimumSize".format(model)),
            "default_system": system,
            "fields": [],
        }

    for row in field_rows:
        model = _text(row.get("DeviceID"))
        if model not in devices:
            continue
        field_type = _text(row.get("FieldType"))
        if field_type not in VALID_FIELD_TYPES:
            raise ExportError("源字段第 {} 行类型无效：{}".format(row["_row"], field_type))
        rule = {"field": _text(row.get("FieldName")), "type": field_type, "priority": _integer(row.get("Priority"), "Priority", True) or 100}
        if rule["field"] not in VALID_SOURCE_FIELDS:
            if rule["field"] not in mapped_source_fields:
                continue  # Documentation-only source field with no target equivalent.
            raise ExportError("源字段第 {} 行 FieldName 无效：{}".format(row["_row"], rule["field"]))
        if field_type != "constant":
            rule["offset"] = _hex(row.get("OffsetHex"), "OffsetHex")
            rule["size"] = _integer(row.get("Size"), "Size", True) or 1
            rule["byte_order"] = _text(row.get("ByteOrder")) or "big"
            if rule["offset"] + rule["size"] > devices[model]["minimum_size"]:
                raise ExportError("{} 的字段 {} 超出 MinimumSize".format(model, rule["field"]))
        bit = _integer(row.get("Bit"), "Bit", True)
        if bit is not None:
            if not 0 <= bit <= 7:
                raise ExportError("Bit 必须在 0..7")
            rule["bit"] = bit
        width = _integer(row.get("BitWidth"), "BitWidth", True)
        if width is not None:
            rule["bit_width"] = width
        if _boolean(row.get("Invert")):
            rule["invert"] = True
        for column, key in (("Scale", "scale"), ("Add", "add"), ("TrueValue", "true_value"), ("FalseValue", "false_value"), ("Constant", "constant")):
            value = _integer(row.get(column), column, True)
            if value is not None:
                rule[key] = value
        if _boolean(row.get("SkipFalse")):
            rule["skip_false"] = True
        skip_values = _hex_list(row.get("SkipValuesHex"), "SkipValuesHex")
        if skip_values:
            rule["skip_values"] = skip_values
        if _boolean(row.get("NullIfZero")):
            rule["null_if_zero"] = True
        divide = _integer(row.get("Divide"), "Divide", True)
        if divide is not None:
            if divide <= 0:
                raise ExportError("Divide 必须大于 0")
            rule["divide"] = divide
        minimum = _integer(row.get("MinimumValue"), "MinimumValue", True)
        if minimum is not None:
            rule["minimum_value"] = minimum
        if field_type in {"bit", "bitfield"} and "bit" not in rule:
            raise ExportError("{} 的字段 {} 必须填写 Bit".format(model, rule["field"]))
        if field_type == "bitfield" and "bit_width" not in rule:
            raise ExportError("{} 的字段 {} 必须填写 BitWidth".format(model, rule["field"]))
        if field_type in {"divisor", "constant"} and "constant" not in rule:
            raise ExportError("{} 的字段 {} 必须填写 Constant".format(model, rule["field"]))
        devices[model]["fields"].append(rule)

    targets = {system: {"system": system, "defaults": {}, "bit_mappings": [], "value_mappings": []} for system in VALID_SYSTEMS}
    occupied = set()
    for row in bit_rows:
        system = _text(row.get("TargetSystem")); operation = _text(row.get("Operation")); register = _text(row.get("TargetRegister"))
        bit_value = row.get("TargetBit")
        if not register and bit_value in (None, ""):
            continue  # Explicitly documented source feature with no target equivalent.
        if not register or bit_value in (None, ""):
            raise ExportError("位映射第 {} 行必须同时填写或同时留空 TargetRegister/TargetBit".format(row["_row"]))
        bit = _integer(bit_value, "TargetBit")
        if system not in targets or operation not in VALID_OPERATIONS or register not in VALID_REGISTERS or not 0 <= bit <= 7:
            raise ExportError("位映射第 {} 行包含无效值".format(row["_row"]))
        key = (system, register, bit)
        if key in occupied:
            raise ExportError("目标位重复写入：{} {} bit{}".format(*key))
        occupied.add(key)
        mapping = {"source_field": _text(row.get("SourceField")), "operation": operation, "target_register": register, "target_bit": bit, "priority": _integer(row.get("Priority"), "Priority", True) or 100}
        if mapping["source_field"] not in VALID_SOURCE_FIELDS:
            raise ExportError("位映射第 {} 行 SourceField 无效".format(row["_row"]))
        compare = _integer(row.get("CompareValue"), "CompareValue", True)
        if compare is not None:
            mapping["compare_value"] = compare
        targets[system]["bit_mappings"].append(mapping)

    for row in register_rows:
        system = _text(row.get("TargetSystem")); register = _text(row.get("Register"))
        if system not in targets or register not in VALID_REGISTERS:
            raise ExportError("寄存器默认值第 {} 行系统或寄存器无效".format(row["_row"]))
        default = _hex(row.get("DefaultValueHex"), "DefaultValueHex", True)
        if default is not None:
            if not 0 <= default <= 0xFF:
                raise ExportError("寄存器默认值必须在 00..FF")
            targets[system]["defaults"][register] = default
        source_field = _text(row.get("SourceField"))
        if source_field:
            if source_field not in VALID_SOURCE_FIELDS:
                raise ExportError("寄存器默认值第 {} 行 SourceField 无效".format(row["_row"]))
            policy = _text(row.get("OutputPolicy")) or "always"; transform = _text(row.get("Transform")) or "direct"
            if policy not in VALID_POLICIES or transform not in VALID_TRANSFORMS:
                raise ExportError("寄存器默认值第 {} 行策略或转换无效".format(row["_row"]))
            targets[system]["value_mappings"].append({"target_register": register, "source_field": source_field, "output_policy": policy, "transform": transform, "parameter": _text(row.get("Parameter")) or None})

    enums = defaultdict(list)
    for row in enum_rows:
        enums[_text(row.get("MapName"))].append({"source": _integer(row.get("SourceValue"), "SourceValue"), "target": _hex(row.get("TargetValueHex"), "TargetValueHex")})

    output_dir.mkdir(parents=True, exist_ok=True)
    documents = {
        "devices.json": {"schema_version": 1, "devices": list(devices.values())},
        "targets.json": {"schema_version": 1, "targets": [targets[name] for name in sorted(targets)]},
        "enums.json": {"schema_version": 1, "enums": dict(enums)},
    }
    for filename, document in documents.items():
        (output_dir / filename).write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("已导出 {} 个设备、{} 个目标系统到 {}".format(len(devices), len(targets), output_dir))


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="校验设备规则 Excel 并导出运行时 JSON")
    parser.add_argument("workbook", type=Path, nargs="?", default=root / "profiles" / "设备规则.xlsx")
    parser.add_argument("-o", "--output", type=Path, default=root / "profiles" / "generated")
    args = parser.parse_args()
    try:
        export_profiles(args.workbook, args.output)
    except (ExportError, OSError, zipfile.BadZipFile) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
