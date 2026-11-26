"""Comprehensive unit & integration test suite for DEX // Mark LVII AURA TERMINAL."""

from __future__ import annotations

import datetime
import json
import re
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import main as app_main
import tui as aura_tui
from core import action_loader, plugin_loader
from core.platform_support import parse_os_release
from core.routines import engine as routines_engine
from core.tasks import engine as tasks_engine
from core.tasks import store as tasks_store
from memory import config_manager, memory_manager
from providers.audio import compute_waveform_bars, render_waveform_glyphs
from providers.engine_pipeline import PipelineEngine

ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def _visible_len(s: str) -> int:
    return len(ANSI_RE.sub("", s))


class AuraTerminalTests(unittest.TestCase):
    def test_parse_os_release_all_supported_distros(self) -> None:
        samples = [
            ('ID=zorin\nPRETTY_NAME="Zorin OS 17.2"\nID_LIKE=ubuntu', "zorin", "Zorin OS"),
            ('ID=ubuntu\nPRETTY_NAME="Ubuntu 24.04 LTS"\nID_LIKE=debian', "ubuntu", "Ubuntu"),
            ('ID=linuxmint\nPRETTY_NAME="Linux Mint 22"\nID_LIKE=ubuntu', "linuxmint", "Linux Mint"),
            ('ID=debian\nPRETTY_NAME="Debian GNU/Linux 12"', "debian", "Debian"),
            ('ID=fedora\nPRETTY_NAME="Fedora Linux 41"', "fedora", "Fedora"),
            ('ID=arch\nPRETTY_NAME="Arch Linux"', "arch", "Arch Linux"),
            ('ID=endeavouros\nPRETTY_NAME="EndeavourOS"', "endeavouros", "EndeavourOS"),
            ('ID="opensuse-tumbleweed"\nPRETTY_NAME="openSUSE Tumbleweed"\nID_LIKE="opensuse suse"', "opensuse-tumbleweed", "openSUSE Tumbleweed"),
        ]
        for content, expected_id, expected_name in samples:
            parsed = parse_os_release(content)
            self.assertEqual(parsed["id"], expected_id)
            self.assertEqual(parsed["supported_name"], expected_name)
            self.assertTrue(parsed["is_supported_linux"])

    def test_non_destructive_config_backup_and_restore(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            settings_file = tmp_path / "settings.json"
            keys_file = tmp_path / "api_keys.json"
            backups_dir = tmp_path / "backups"

            # Pre-existing legacy config must keep existing user choices on load
            settings_file.write_text(json.dumps({"active_suit": "mark50", "theme": "electric_cobalt"}), encoding="utf-8")

            with mock.patch.object(config_manager, "CONFIG_DIR", tmp_path), \
                 mock.patch.object(config_manager, "SETTINGS_FILE", settings_file), \
                 mock.patch.object(config_manager, "API_KEYS_FILE", keys_file), \
                 mock.patch.object(config_manager, "BACKUPS_DIR", backups_dir):
                loaded = config_manager.load_settings()
                self.assertEqual(loaded["active_suit"], "mark50")
                self.assertEqual(loaded["theme"], "electric_cobalt")
                self.assertEqual(loaded["assistant_name"], "DEX")

                backup_path = config_manager.export_config_backup("testsnap")
                self.assertTrue(backup_path.exists())
                self.assertGreaterEqual(len(config_manager.list_config_backups()), 1)

                # Modify settings and then restore backup
                loaded["theme"] = "ultraviolet_pulse"
                config_manager.save_settings(loaded)
                self.assertEqual(config_manager.load_settings()["theme"], "ultraviolet_pulse")

                self.assertTrue(config_manager.restore_config_backup(backup_path))
                self.assertEqual(config_manager.load_settings()["theme"], "electric_cobalt")

                # Masked API key handling
                config_manager.save_api_key("GEMINI_API_KEY", "AIzaSyTestSecretKey9876")
                self.assertEqual(config_manager.mask_key("AIzaSyTestSecretKey9876"), "AIza...9876")
                self.assertEqual(config_manager.load_api_keys()["GEMINI_API_KEY"], "AIzaSyTestSecretKey9876")

    def test_non_destructive_memory_crud(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mem_file = Path(tmp) / "long_term.json"
            mem_file.write_text(
                json.dumps({
                    "identity": {"assistant": "DEX", "owner": "Operator"},
                    "facts": [{"id": "mem_000001", "category": "general", "text": "Existing user fact", "created_at": "2026-01-01 09:00"}],
                    "monitors": [],
                    "sessions": [],
                }),
                encoding="utf-8",
            )
            with mock.patch.object(memory_manager, "MEMORY_FILE", mem_file):
                e2 = memory_manager.add_fact("Linux distro is Fedora", category="system")
                all_facts = memory_manager.load_memory()["facts"]
                self.assertEqual(len(all_facts), 2)
                self.assertEqual(all_facts[0]["text"], "Existing user fact")

                hits = memory_manager.search_facts("fedora")
                self.assertEqual(len(hits), 1)

                removed = memory_manager.remove_fact(e2["id"])
                self.assertIsNotNone(removed)
                self.assertEqual(len(memory_manager.load_memory()["facts"]), 1)

                cleared = memory_manager.clear_memory_facts()
                self.assertEqual(cleared, 1)
                self.assertEqual(len(memory_manager.load_memory()["facts"]), 0)

    def test_plugin_ast_quarantine_and_toggle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdir = tmp_path / "plugins"
            pdir.mkdir()
            settings_file = tmp_path / "settings.json"

            # Template file must always be skipped
            (pdir / "_template.py").write_text("TOOL={'name':'skip'}\ndef handler(c,a,x): pass\n", encoding="utf-8")

            # Untrusted plugin with subprocess must be AST-quarantined until approved
            risky = pdir / "custom_shell.py"
            risky.write_text(
                "import subprocess\n"
                "TOOL = {'name': 'custom_shell', 'description': 'Risky', 'commands': ['cshell']}\n"
                "def handler(cmd, arg, ctx):\n"
                "    return None\n",
                encoding="utf-8",
            )

            with mock.patch.object(config_manager, "CONFIG_DIR", tmp_path), \
                 mock.patch.object(config_manager, "SETTINGS_FILE", settings_file), \
                 mock.patch.object(plugin_loader, "PLUGINS_DIR", pdir):
                records = plugin_loader.inspect_all_plugins()
                self.assertEqual(len(records), 1)
                self.assertEqual(records[0]["status"], "quarantined")
                self.assertIn("import subprocess", records[0]["risky_patterns"])

                # Approve then verify active
                plugin_loader.approve_plugin("custom_shell")
                records_after = plugin_loader.inspect_all_plugins()
                self.assertEqual(records_after[0]["status"], "active")

                # Disable then verify disabled
                enabled, _ = plugin_loader.toggle_plugin("custom_shell")
                self.assertFalse(enabled)
                self.assertEqual(plugin_loader.inspect_all_plugins()[0]["status"], "disabled")

    def test_tasks_and_routines_scheduler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            tasks_dir = tmp_path / "tasks"
            reports_dir = tmp_path / "reports"
            reports_dir.mkdir(parents=True, exist_ok=True)

            with mock.patch.object(tasks_store, "BASE_DIR", tmp_path), \
                 mock.patch.object(tasks_store, "TASKS_DIR", tasks_dir), \
                 mock.patch.object(tasks_engine, "BASE_DIR", tmp_path):
                t = tasks_engine.start_task("Verify Linux audio subsystem")
                self.assertEqual(t["status"], "completed")
                self.assertTrue((tmp_path / t["report_file"]).exists())

                steered = tasks_engine.steer_task(t["id"], "Include PipeWire notes")
                self.assertEqual(len(steered["notes"]), 1)

                cancelled = tasks_engine.cancel_task(t["id"])
                self.assertEqual(cancelled["status"], "cancelled")

                resumed = tasks_engine.resume_task(t["id"])
                self.assertEqual(resumed["status"], "completed")

        past = (datetime.datetime.now() - datetime.timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M")
        future = (datetime.datetime.now() + datetime.timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M")
        self.assertTrue(routines_engine.is_routine_due({"enabled": True, "next_fire": past}))
        self.assertFalse(routines_engine.is_routine_due({"enabled": True, "next_fire": future}))
        self.assertFalse(routines_engine.is_routine_due({"enabled": False, "next_fire": past}))

    def test_waveform_math_and_pipeline_engine(self) -> None:
        silence = struct.pack("<240h", *([0] * 240))
        loud = struct.pack("<240h", *([18000, -18000] * 120))
        self.assertEqual(compute_waveform_bars(silence, bars=12), [0] * 12)
        loud_bars = compute_waveform_bars(loud, bars=12, gain=1.0)
        self.assertEqual(len(loud_bars), 12)
        self.assertTrue(all(b >= 4 for b in loud_bars))
        glyphs = render_waveform_glyphs(loud_bars)
        self.assertEqual(len(glyphs), 12)

        class _FakeSTT:
            def is_available(self) -> bool:
                return True

            def transcribe(self, _pcm: bytes) -> tuple[bool, str]:
                return True, "run diagnostics"

        class _FakeTTS:
            def is_available(self) -> bool:
                return True

            def speak(self, text: str) -> tuple[bool, str]:
                return True, f"Spoke {len(text)} chars"

        pipe = PipelineEngine(stt=_FakeSTT(), llm_fn=lambda q: f"Confirmed: {q}", tts=_FakeTTS())
        events = pipe.process_audio(loud)
        kinds = [e.kind for e in events]
        self.assertEqual(kinds, ["text", "text", "audio", "done"])
        self.assertIn("Confirmed: run diagnostics", events[1].text)

    def test_openwakeword_hey_dex_detection_and_cooldown(self) -> None:
        from providers.wakeword_oww import OpenWakeWordProvider

        # Without openwakeword package installed, availability_detail must truthfully report ready=False
        uninstalled = OpenWakeWordProvider(phrase="hey dex")
        detail = uninstalled.availability_detail()
        self.assertEqual(detail["phrase"], "hey dex")
        self.assertFalse(detail["ready"])

        class _FakeOWWModel:
            def __init__(self) -> None:
                self.scores: list[float] = [0.12, 0.86, 0.91, 0.88]

            def predict(self, _samples: object) -> dict[str, float]:
                score = self.scores.pop(0)
                return {"hey_dex": score}

        oww = OpenWakeWordProvider(phrase="hey dex", threshold=0.5, cooldown_s=2.0, model=_FakeOWWModel())
        self.assertTrue(oww.is_available())
        pcm_chunk = struct.pack("<1280h", *([500] * 1280))

        # 1) Below threshold -> False
        hit1, s1, lbl1 = oww.process_pcm16(pcm_chunk, now_ts=10.0)
        self.assertFalse(hit1)
        self.assertAlmostEqual(s1, 0.12, places=2)
        self.assertEqual(lbl1, "hey_dex")

        # 2) Above threshold -> True
        hit2, s2, _ = oww.process_pcm16(pcm_chunk, now_ts=11.0)
        self.assertTrue(hit2)
        self.assertGreaterEqual(s2, 0.85)

        # 3) Within cooldown -> False
        hit3, _s3, _ = oww.process_pcm16(pcm_chunk, now_ts=12.0)
        self.assertFalse(hit3)

        # 4) After cooldown -> True
        hit4, _s4, _ = oww.process_pcm16(pcm_chunk, now_ts=13.5)
        self.assertTrue(hit4)

        res = app_main.dispatch_command("wakeword status")
        self.assertEqual(res["mode"], "local")
        self.assertTrue(any("hey dex" in ln for ln in res["lines"]))

    def test_tui_screens_render_cleanly_with_aligned_borders(self) -> None:
        t = app_main.collect_snapshot()
        arch = app_main.build_architecture_snapshot()
        w = 94
        screens = [
            aura_tui.render_startup_screen(t, arch, w),
            aura_tui.render_dashboard(t, arch, ["[ONLINE] Test event"], w),
            aura_tui.render_chat_screen(t, ["YOU > diag", "DEX > All systems nominal"], w),
            aura_tui.render_plugins_screen(t, arch, 0, w, module_tab="plugins", show_detail=True),
            aura_tui.render_plugins_screen(t, arch, 0, w, module_tab="actions", show_detail=True),
            aura_tui.render_memory_screen(t, arch, 0, w, sub_tab="memory"),
            aura_tui.render_memory_screen(t, arch, 0, w, sub_tab="tasks"),
            aura_tui.render_settings_screen(t, arch, 0, 0, w, status_note="Ready"),
            aura_tui.render_settings_screen(t, arch, 5, 4, w, status_note="Voice & Wake Word"),
            aura_tui.render_voice_screen(t, arch, w, voice_state="IDLE", waveform_bars=[0] * 24),
            aura_tui.render_armor_screen(t, app_main.dispatch_command("diag").get("lines", []), w),
        ]
        self.assertIn("██████╗", screens[0])  # DEX ASCII block logo
        self.assertIn("hey dex", screens[9])  # Voice screen displays wake phrase status
        for scr in screens:
            for line in scr.splitlines():
                self.assertEqual(_visible_len(line), w, f"Border misalignment on line: {line!r}")

        prompt = app_main.render_system_prompt(len(arch["actions"]), len(arch["plugins"]))
        self.assertIn("DEX", prompt)
        self.assertIn("AURA TERMINAL", prompt)


if __name__ == "__main__":
    unittest.main()
