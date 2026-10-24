import csv
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import monitor_core as core


class MonitorTests(unittest.TestCase):
    def test_nvidia_missing_is_unavailable_not_zero(self):
        result = core.gpu_snapshot(which=lambda _: None)
        self.assertEqual(result["gpu_status"], "UNAVAILABLE")
        self.assertIsNone(result["gpu_percent"])

    def test_nvidia_measured_and_shell_free(self):
        runner = Mock(return_value=SimpleNamespace(
            returncode=0, stdout="42, 512, 4096, 57\n", stderr=""))
        result = core.gpu_snapshot(which=lambda _: "nvidia-smi.exe", runner=runner)
        self.assertEqual(result["gpu_percent"], 42.0)
        self.assertEqual(result["gpu_temp_c"], 57.0)
        self.assertEqual(result["gpu_status"], "MEASURED_NVIDIA_GPU_0")
        self.assertEqual(runner.call_args.args[0][0], "nvidia-smi.exe")
        self.assertEqual(runner.call_args.kwargs["timeout"], 3)

    def test_nvidia_bad_output_is_not_fabricated(self):
        runner = Mock(return_value=SimpleNamespace(returncode=1, stdout="", stderr="bad"))
        self.assertIsNone(core.gpu_snapshot(which=lambda _: "nvidia-smi", runner=runner)["gpu_percent"])

    def test_local_snapshot_and_process_memory(self):
        process = SimpleNamespace(info={
            "pid": 8, "name": "game.exe", "memory_info": SimpleNamespace(rss=10485760)})
        fake = Mock()
        fake.cpu_percent.return_value = 82.0
        fake.virtual_memory.return_value = SimpleNamespace(percent=60.0, used=60, total=100)
        fake.disk_usage.return_value = SimpleNamespace(percent=40.0)
        fake.process_iter.return_value = [process]
        with patch.object(core, "psutil", fake):
            result = core.sample(gpu_reader=lambda: core.gpu_snapshot(which=lambda _: None))
        self.assertEqual(result["cpu_percent"], 82.0)
        self.assertEqual(result["top_processes"][0]["memory_mib"], 10.0)
        self.assertNotIn("local_ai_detected", result)
        self.assertIsNone(result["cpu_temp_c"])

    def test_off_by_default_and_stoppable(self):
        mon = core.Monitor(interval=1, sampler=lambda: {"cpu_percent": 10})
        self.assertIsNone(mon.thread)
        self.assertEqual(len(mon.history), 0)
        mon.start()
        mon.stop()
        self.assertTrue(mon.stop_event.is_set())
        self.assertFalse(mon.thread.is_alive())
        mon.clear()
        self.assertEqual(len(mon.history), 0)

    def test_export_only_selected_metrics(self):
        with tempfile.TemporaryDirectory() as d:
            dest = Path(d) / "out.csv"
            core.export_csv([{"cpu_percent": 15, "secret": "DO_NOT_SAVE"}], dest)
            data = dest.read_text(encoding="utf-8-sig")
            self.assertIn("cpu_percent", data)
            self.assertNotIn("DO_NOT_SAVE", data)
            self.assertEqual(next(csv.DictReader(data.splitlines()))["cpu_percent"], "15")

    def test_interval_validation(self):
        for v in (0, 0.2, 31):
            with self.assertRaises(ValueError):
                core.Monitor(interval=v)


if __name__ == "__main__":
    unittest.main()
