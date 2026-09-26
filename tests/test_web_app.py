import json
import unittest
from pathlib import Path

from web_app import build_conversion_payload


T5C2_SAMPLE = bytes.fromhex(
    "54 35 43 32 00 00 00 00 B3 00 44 5A 64 64 FF 00 "
    "5A A5 00 0F 1E 10 03 20 D2 03 14 01 E0 0C 00 00 5A 00"
)


class WebPayloadTests(unittest.TestCase):
    def test_payload_contains_mapping_and_register_bits(self):
        payload = build_conversion_payload(T5C2_SAMPLE)
        self.assertEqual(payload["model"], "T5UIC2")
        self.assertEqual(payload["targetSystem"], "INSTRUCTION")
        self.assertTrue(payload["sourceFields"])
        self.assertTrue(payload["mappings"])
        self.assertEqual(payload["registers"][0]["name"], "R1")
        self.assertEqual(payload["registers"][0]["label"], "波特率索引")
        self.assertEqual(next(row for row in payload["registers"] if row["name"] == "R2")["label"], "触摸屏工作模式")
        self.assertEqual(next(row for row in payload["mappings"] if row["target"] == "R2")["targetLabel"], "触摸屏工作模式")
        self.assertEqual(len(payload["registers"][0]["bits"]), 8)
        self.assertIn("R1=07", payload["text"])

    def test_t5l_payload_requires_explicit_source_model(self):
        data = (Path(__file__).resolve().parents[1] / "T5LCFG.CFG").read_bytes()
        with self.assertRaisesRegex(ValueError, "无法仅凭文件内容区分"):
            build_conversion_payload(data)

    def test_t5uid3_rc_mapping_is_visible(self):
        data = bytearray(16)
        data[:4] = b"T5D3"
        data[8] = 0x48
        data[9:11] = (68).to_bytes(2, "big")
        payload = build_conversion_payload(bytes(data), system="JGUSII")
        rc_rules = [row for row in payload["mappings"] if row["target"] == "RC"]
        self.assertEqual({row["bit"] for row in rc_rules}, {4, 5})
        self.assertEqual(next(row for row in payload["registers"] if row["name"] == "RC")["value"], "30")
        self.assertEqual(next(row for row in payload["registers"] if row["name"] == "R2")["label"], "系统配置")
        self.assertEqual(next(row for row in payload["mappings"] if row["target"] == "R2")["targetLabel"], "系统配置")


if __name__ == "__main__":
    unittest.main()
