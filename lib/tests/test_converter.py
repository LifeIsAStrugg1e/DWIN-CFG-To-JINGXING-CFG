import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from converter import (
    AmbiguousModelError,
    ConfigError,
    UnknownModelError,
    UnsupportedModelError,
    convert_to_jgxing,
    detect_model,
    generate_config_txt,
    parse_dwin_config,
)


T5C2_SAMPLE = bytes.fromhex(
    "54 35 43 32 00 00 00 00 B3 00 44 5A 64 64 FF 00 "
    "5A A5 00 0F 1E 10 03 20 D2 03 14 01 E0 0C 00 00 5A 00"
)


class ConverterTests(unittest.TestCase):
    def test_detects_and_parses_t5uic2(self):
        self.assertEqual(detect_model(T5C2_SAMPLE), "T5UIC2")
        parsed = parse_dwin_config(T5C2_SAMPLE)
        self.assertEqual(parsed.model, "T5UIC2")
        self.assertEqual(parsed.baudrate, 115200)
        self.assertEqual(parsed.direction, 0)
        self.assertEqual(parsed.brightness_on, 64)

    def test_generates_instruction_config(self):
        parsed = parse_dwin_config(T5C2_SAMPLE)
        output = generate_config_txt(
            convert_to_jgxing(parsed, "INSTRUCTION"), "INSTRUCTION"
        )
        self.assertIn("R1=07\n", output)
        self.assertIn("R6=28\n", output)
        self.assertIn("R12=01\n", output)
        self.assertNotIn("RA=", output)

    def test_unknown_header_is_rejected(self):
        with self.assertRaises(UnknownModelError):
            parse_dwin_config(b"OTHER")

    def test_t5l_requires_explicit_source_model(self):
        with self.assertRaises(AmbiguousModelError):
            parse_dwin_config(b"T5LC1" + bytes(20))

    def test_detected_model_without_parser_is_rejected(self):
        with self.assertRaises(UnsupportedModelError):
            parse_dwin_config(b"T5D1" + bytes(20))

    def test_aiot_direct_baud_does_not_invent_optional_files(self):
        data = bytearray(0x23)
        data[:5] = b"AIoT1"
        data[0x0C:0x0F] = bytes((0x01, 0xC2, 0x00))
        data[0x0F] = 0x40
        parsed = parse_dwin_config(bytes(data))
        output = generate_config_txt(
            convert_to_jgxing(parsed, "INSTRUCTION"), "INSTRUCTION"
        )
        self.assertIn("R1=07\n", output)
        self.assertIn("R6=3F\n", output)
        self.assertNotIn("R10=", output)
        self.assertNotIn("R11=", output)

    def test_unsupported_baud_is_rejected(self):
        parsed = parse_dwin_config(T5C2_SAMPLE)
        parsed.baudrate = 12345
        with self.assertRaisesRegex(ConfigError, "不支持波特率"):
            convert_to_jgxing(parsed, "INSTRUCTION")

    def test_register_values_are_limited_to_one_byte(self):
        parsed = parse_dwin_config(T5C2_SAMPLE)
        parsed.backlight_time = 1000
        result = convert_to_jgxing(parsed, "INSTRUCTION")
        self.assertEqual(result.R8, 0xFF)

    def test_instruction_crc_bit_uses_inverted_target_semantics(self):
        disabled = bytearray(0x23)
        disabled[:5] = b"AIoT1"
        disabled[0x0C:0x0F] = bytes((0x01, 0xC2, 0x00))
        enabled = bytearray(disabled)
        enabled[0x05] = 0x80

        disabled_result = convert_to_jgxing(
            parse_dwin_config(bytes(disabled)), "INSTRUCTION"
        )
        enabled_result = convert_to_jgxing(
            parse_dwin_config(bytes(enabled)), "INSTRUCTION"
        )

        self.assertEqual(disabled_result.R3 & 0x02, 0x02)
        self.assertEqual(enabled_result.R3 & 0x02, 0x00)


if __name__ == "__main__":
    unittest.main()
