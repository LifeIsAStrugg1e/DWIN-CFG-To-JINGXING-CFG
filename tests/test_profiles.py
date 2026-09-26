import json
import tempfile
import unittest
from pathlib import Path

from lib.converter import convert_to_jgxing, parse_dwin_config
from tools.export_profiles import export_profiles


ROOT = Path(__file__).resolve().parents[1]


class ProfileExportTests(unittest.TestCase):
    def test_workbook_exports_expected_devices(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            export_profiles(ROOT / "profiles" / "设备规则.xlsx", output)
            devices = json.loads((output / "devices.json").read_text(encoding="utf-8"))
            models = {item["model"] for item in devices["devices"]}
            self.assertEqual(models, {"T5UIC2", "T5UID3", "T5L_DGUSII", "T5L_TA"})
            self.assertTrue((output / "targets.json").is_file())
            self.assertTrue((output / "enums.json").is_file())


class DataDrivenDeviceTests(unittest.TestCase):
    def test_t5l_profiles_preserve_legacy_conversion(self):
        data = (ROOT / "T5LCFG.CFG").read_bytes()

        dgus = parse_dwin_config(data, "T5L_DGUSII")
        dgus_result = convert_to_jgxing(dgus, "JGUSII")
        self.assertEqual((dgus.baudrate, dgus.direction, dgus.bg_image_id), (19200, 0, 32))
        self.assertIs(dgus.tp_auto_upload, True)
        self.assertIs(dgus.backlight_standby, False)
        self.assertEqual((dgus.backlight_time, dgus_result.R1, dgus_result.R2, dgus_result.RC), (5, 0x04, 0x0C, 0x20))

        ta = parse_dwin_config(data, "T5L_TA")
        ta_result = convert_to_jgxing(ta, "INSTRUCTION")
        self.assertEqual((ta.baudrate, ta.direction, ta.bg_image_id, ta.audio_id), (19200, 0, 32, None))
        self.assertEqual((ta_result.R1, ta_result.R2, ta_result.R3, ta_result.R8), (0x04, 0x08, 0x02, 0x0A))

    def test_t5l_profile_sentinel_values_keep_defaults(self):
        data = bytearray(16)
        data[:5] = b"T5LC1"
        data[14:16] = b"\xFF\xFF"
        parsed = parse_dwin_config(bytes(data), "T5L_DGUSII")
        self.assertEqual(parsed.baudrate, 115200)
        self.assertEqual(parsed.backlight_time, 5)
        self.assertIsNone(parsed.bg_image_id)

    def test_t5uid3_source_fields_and_target_bits(self):
        data = bytearray(16)
        data[:4] = b"T5D3"
        data[8] = 0xED  # upload, 128 vars, load22, buzzer, standby, 90 degrees
        data[9:11] = (68).to_bytes(2, "big")  # 7833600 / 68 = 115200

        parsed = parse_dwin_config(bytes(data))
        result = convert_to_jgxing(parsed, "JGUSII")

        self.assertEqual(parsed.model, "T5UID3")
        self.assertEqual(parsed.direction, 90)
        self.assertEqual(parsed.var_per_page, 128)
        self.assertEqual(result.R1, 0x07)
        self.assertEqual(result.R2, 0xAC)

    def test_rc_is_generated_from_target_bit_rules(self):
        data = bytearray(16)
        data[:4] = b"T5D3"
        data[8] = 0x48  # 128 variables and touch buzzer
        data[9:11] = (68).to_bytes(2, "big")

        parsed = parse_dwin_config(bytes(data))
        result = convert_to_jgxing(parsed, "JGUSII")

        self.assertEqual(result.RC, 0x30)

    def test_var_per_page_sets_rc_bit4_only_for_128(self):
        data_64 = bytearray(16)
        data_64[:4] = b"T5D3"
        data_64[9:11] = (68).to_bytes(2, "big")
        data_128 = bytearray(data_64)
        data_128[8] = 0x40

        result_64 = convert_to_jgxing(parse_dwin_config(bytes(data_64)), "JGUSII")
        result_128 = convert_to_jgxing(parse_dwin_config(bytes(data_128)), "JGUSII")

        self.assertEqual(result_64.RC & 0x10, 0x00)
        self.assertEqual(result_128.RC & 0x10, 0x10)


if __name__ == "__main__":
    unittest.main()
