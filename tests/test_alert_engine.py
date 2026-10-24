"""Local alert regression, no GUI, drivers, network or notification access."""
import json
import math
import tempfile
import unittest
from pathlib import Path

from alert_engine import (AlertEngine, Rule, default_rules, metric_value,
                          read_rules, save_rules)


class AlertEngineTests(unittest.TestCase):
    def test_sustained_cooldown_repeat_recovery(self):
        eng = AlertEngine([Rule("cpu", "cpu_percent", 80, 30, 300)])
        self.assertEqual(eng.process({"cpu_percent": 90}, now=0), [])
        self.assertEqual(eng.process({"cpu_percent": 90}, now=29), [])
        events = eng.process({"cpu_percent": 90}, now=30)
        self.assertEqual([e.kind for e in events], ["ALERT"])
        self.assertEqual(eng.process({"cpu_percent": 91}, now=32), [])
        self.assertEqual([e.kind for e in eng.process({"cpu_percent": 90}, now=330)], ["REPEAT"])
        self.assertEqual([e.kind for e in eng.process({"cpu_percent": 10}, now=331)], ["RECOVERED"])
        self.assertEqual(eng.process({"cpu_percent": 10}, now=333), [])
        self.assertEqual(eng.process({"cpu_percent": 90}, now=334), [])
        self.assertEqual([e.kind for e in eng.process({"cpu_percent": 90}, now=364)], ["ALERT"])

    def test_unavailable_gpu_does_not_warn_or_fake_recovery(self):
        eng = AlertEngine([Rule("gpu", "gpu_percent", 80, 0)])
        self.assertEqual(eng.process({"gpu_percent": None}, now=0), [])
        self.assertEqual(eng.process({"gpu_percent": 95}, now=1)[0].kind, "ALERT")
        self.assertEqual(eng.process({"gpu_percent": None}, now=2), [])
        self.assertEqual(eng.process({"gpu_percent": 0}, now=3), [])

    def test_snooze_blocks_alerts_and_resumes(self):
        eng = AlertEngine([Rule("ram", "ram_percent", 85, 0)])
        eng.snooze(10, now=100)
        self.assertEqual(eng.process({"ram_percent": 99}, now=101), [])
        self.assertEqual(eng.process({"ram_percent": 99}, now=699), [])
        self.assertEqual(eng.process({"ram_percent": 99}, now=700)[0].kind, "ALERT")

    def test_missing_gpu_vram_uses_none_not_zero(self):
        sample = {"gpu_percent": None, "vram_total_mib": None,
                  "vram_used_mib": None}
        self.assertIsNone(metric_value(sample, "gpu_percent"))
        self.assertIsNone(metric_value(sample, "vram_free_mib"))
        eng = AlertEngine([Rule("vram", "vram_free_mib", 1024, 0)])
        self.assertEqual(eng.process(sample, now=0), [])
        self.assertEqual(eng.process({"vram_total_mib": 8096, "vram_used_mib": 7996}, now=1)[0].kind, "ALERT")

    def test_ai_candidate_is_not_inferred_from_games(self):
        eng = AlertEngine([Rule("ai", "ai_candidate_present", 1, 0),
                           Rule("aicpu", "ai_cpu_high", 85, 10)])
        self.assertEqual(eng.process({"cpu_percent": 99, "top_processes": [{"name": "game.exe"}],
                                      "local_ai_related_process_candidates": []}, now=0), [])
        sample = {"cpu_percent": 90, "local_ai_related_process_candidates": [{"pid": 1, "name": "ollama.exe"}]}
        self.assertEqual([e.rule_id for e in eng.process(sample, now=1)], ["ai"])
        self.assertEqual([e.rule_id for e in eng.process(sample, now=11)], ["aicpu"])
        restored = {"cpu_percent": 10, "local_ai_related_process_candidates": []}
        self.assertEqual({e.kind for e in eng.process(restored, now=12)}, {"RECOVERED"})

    def test_process_name_exact_and_memory(self):
        eng = AlertEngine([Rule("exe", "process_present", 1, 0, target="myapp.exe"),
                           Rule("rss", "process_memory_mib", 500, 0, target="myapp.exe")])
        self.assertEqual(eng.process({"observed_processes": [{"name": "myapp.exe-evil", "memory_mib": 999}]}, now=0), [])
        records = {"observed_processes": [{"name": "MyApp.exe", "memory_mib": 600}]}
        self.assertEqual({e.rule_id for e in eng.process(records, now=1)}, {"exe", "rss"})
        self.assertEqual({e.kind for e in eng.process({"observed_processes": []}, now=2)}, {"RECOVERED"})

    def test_process_missing_telemetry_is_not_shutdown(self):
        eng = AlertEngine([Rule("exe", "process_present", 1, 0, target="myapp.exe")])
        self.assertEqual(eng.process({}, now=0), [])
        self.assertEqual(eng.process({"observed_processes": [{"name": "myapp.exe", "memory_mib": 1}]}, now=1)[0].kind, "ALERT")
        self.assertEqual(eng.process({}, now=2), [])

    def test_alerts_off_rules_disabled(self):
        rule = Rule("cpu", "cpu_percent", 85, 0, enabled=False)
        eng = AlertEngine([rule])
        self.assertEqual(eng.process({"cpu_percent": 100}, now=0), [])

    def test_reconfigure_resets_stale_duration(self):
        eng = AlertEngine([Rule("cpu", "cpu_percent", 85, 30)])
        eng.process({"cpu_percent": 100}, now=0)
        eng.replace_rules([Rule("cpu", "cpu_percent", 70, 30)])
        self.assertEqual(eng.process({"cpu_percent": 100}, now=20), [])
        self.assertEqual(eng.process({"cpu_percent": 100}, now=50)[0].kind, "ALERT")

    def test_validations(self):
        for rule in [Rule("x", "gpu_percent", float("nan"), 0),
                     Rule("x", "gpu_percent", 95, -1),
                     Rule("x", "gpu_percent", 95, 0, cooldown_s=10),
                     Rule("x", "bad_metric", 50, 0),
                     Rule("x", "process_present", 1, 0, target="bad;rm")]:
            with self.assertRaises(ValueError):
                rule.validate()
        with self.assertRaises(ValueError):
            AlertEngine([Rule("x", "cpu_percent", 85, 0), Rule("x", "ram_percent", 90, 0)])

    def test_roundtrip_save_explicit_then_read(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "rules.json"
            default = read_rules("CPU_GPU_Monitor", destination=path)
            self.assertFalse(default[1])
            self.assertFalse(default[2])
            rules = default_rules()
            save_rules("CPU_GPU_Monitor", rules, True, True, destination=path)
            loaded, enabled, toast = read_rules("CPU_GPU_Monitor", destination=path)
            self.assertEqual(loaded, rules)
            self.assertTrue(enabled)
            self.assertTrue(toast)

    def test_bad_config_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "rules.json"
            path.write_text('{"schema":999,"rules":[]}', encoding="utf-8")
            _, enabled, toast = read_rules("AI_PC_Monitor", destination=path)
            self.assertFalse(enabled)
            self.assertFalse(toast)

    def test_history_bounded(self):
        eng = AlertEngine([Rule("c", "cpu_percent", 1, 0, cooldown_s=30)])
        for i in range(220):
            eng.process({"cpu_percent": 100}, now=i * 31)
        self.assertLessEqual(len(eng.history), 200)

    def test_default_ai_rules_do_not_require_unavailable_gpu(self):
        rules = default_rules(ai=True)
        self.assertTrue(any(r.metric == "ai_candidate_present" for r in rules))
        self.assertFalse(next(r.enabled for r in rules if r.metric == "gpu_percent"))


if __name__ == "__main__":
    unittest.main()
