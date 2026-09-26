import tempfile
import unittest
from pathlib import Path

from cfg_convert_tools import CfgConvertError, convert_cfg, generate_config_text


T5C2_SAMPLE = bytes.fromhex(
    "54 35 43 32 00 00 00 00 B3 00 44 5A 64 64 FF 00 "
    "5A A5 00 0F 1E 10 03 20 D2 03 14 01 E0 0C 00 00 5A 00"
)


class GenerateConfigTextTests(unittest.TestCase):
    def test_t5l_sample_requires_source_model(self):
        root = Path(__file__).resolve().parents[1]
        data = (root / "T5LCFG.CFG").read_bytes()
        with self.assertRaisesRegex(CfgConvertError, "无法仅凭文件内容区分"):
            generate_config_text(data)

    def test_t5l_dgusii_sample(self):
        root = Path(__file__).resolve().parents[1]
        text = generate_config_text(
            (root / "T5LCFG.CFG").read_bytes(), "T5L_DGUSII"
        )
        self.assertIn("R1=04\n", text)
        self.assertIn("R2=0C\n", text)
        self.assertIn("R8=05\n", text)
        self.assertIn("R10=20\n", text)
        self.assertNotIn("R11=", text)
        self.assertNotIn("R8=28F", text)

    def test_t5uic2_uses_two_byte_baud_divisor(self):
        text = generate_config_text(T5C2_SAMPLE)
        self.assertIn("R1=07\n", text)
        self.assertIn("R6=28\n", text)
        self.assertIn("R12=01\n", text)
        self.assertNotIn("RA=", text)

    def test_unknown_device_is_rejected(self):
        with self.assertRaisesRegex(CfgConvertError, "无法识别"):
            generate_config_text(b"unknown")

    def test_known_but_unsupported_device_is_rejected(self):
        with self.assertRaisesRegex(CfgConvertError, "尚无可靠解析规则"):
            generate_config_text(b"T5C1" + bytes(20))

    def test_truncated_known_device_is_rejected(self):
        with self.assertRaisesRegex(CfgConvertError, "至少需要 16 字节"):
            generate_config_text(b"T5LC1", "T5L_DGUSII")


class ConvertCfgTests(unittest.TestCase):
    def test_default_output_is_next_to_input(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "device.CFG"
            source.write_bytes(T5C2_SAMPLE)
            result = convert_cfg(source)
            self.assertEqual(result, source.with_name("config.TXT"))
            self.assertIn("R1=07\n", result.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
