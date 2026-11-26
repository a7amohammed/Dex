"""Non-destructive configuration, API keys, and backup/restore manager for DEX (Mark LVII)."""

from __future__ import annotations

import copy
import datetime
import json
import os
import time
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
API_KEYS_FILE = CONFIG_DIR / "api_keys.json"
BACKUPS_DIR = CONFIG_DIR / "backups"

MARK_SUITS: dict[str, dict[str, Any]] = {
    "mark3": {
        "id": "mark3",
        "designation": "Mark III",
        "codename": "Gold-Titanium Alloy",
        "core": "Palladium Arc Reactor Mk II",
        "max_mach": 2.1,
        "armor_integrity": 98.4,
        "power_output_gw": 3.0,
        "notes": "Classic red-and-gold orbital high-altitude frame.",
    },
    "mark7": {
        "id": "mark7",
        "designation": "Mark VII",
        "codename": "Heavy Deployment",
        "core": "New Element Arc Reactor",
        "max_mach": 3.4,
        "armor_integrity": 99.1,
        "power_output_gw": 5.2,
        "notes": "Autonomous wrist-band lock-on deployment suit.",
    },
    "mark42": {
        "id": "mark42",
        "designation": "Mark XLII",
        "codename": "Prodigal Son",
        "core": "Vibranium-Core Micro Reactor",
        "max_mach": 3.8,
        "armor_integrity": 96.7,
        "power_output_gw": 6.4,
        "notes": "Prehensile modular propulsion assembly.",
    },
    "mark50": {
        "id": "mark50",
        "designation": "Mark L",
        "codename": "Bleeding Edge",
        "core": "RT-Nanotech Node",
        "max_mach": 8.5,
        "armor_integrity": 99.8,
        "power_output_gw": 11.4,
        "notes": "Self-assembling nanotech weapon and shield matrix.",
    },
    "mark57": {
        "id": "mark57",
        "designation": "Mark LVII",
        "codename": "AURA Terminal Core",
        "core": "Dual-Node Nanotech RT",
        "max_mach": 9.4,
        "armor_integrity": 100.0,
        "power_output_gw": 13.6,
        "notes": "Modular Linux terminal architecture with Gemini Live, plugins, routines, and background agents.",
    },
    "mark85": {
        "id": "mark85",
        "designation": "Mark LXXXV",
        "codename": "Endgame Final Frame",
        "core": "High-Output Nanotech RT",
        "max_mach": 10.2,
        "armor_integrity": 100.0,
        "power_output_gw": 14.8,
        "notes": "Peak Stark Industries nanotech defense & energy channeling chassis.",
    },
}

THEMES: dict[str, dict[str, str]] = {
    "cyberpunk_aura": {
        "label": "Cyberpunk Aura (Cyan / Purple)",
        "primary": "0;240;255",
        "secondary": "56;189;248",
        "accent": "168;85;247",
        "border": "168;85;247",
    },
    "electric_cobalt": {
        "label": "Electric Cobalt (Blue / Cyan)",
        "primary": "56;189;248",
        "secondary": "37;99;235",
        "accent": "129;140;248",
        "border": "59;130;246",
    },
    "ultraviolet_pulse": {
        "label": "Ultraviolet Pulse (Purple / Cyan)",
        "primary": "192;132;252",
        "secondary": "0;240;255",
        "accent": "59;130;246",
        "border": "147;51;234",
    },
}

DEFAULT_SETTINGS: dict[str, Any] = {
    "assistant_name": "DEX",
    "user_name": "Operator",
    "active_suit": "mark57",
    "protocol": "STANDBY",
    "subsystems": {
        "reactor": 96,
        "repulsors": 84,
        "thrusters": 78,
        "shielding": 90,
        "sensors": 95,
    },
    "quiet_hours": {"start": 23, "end": 7, "enabled": False},
    "theme": "cyberpunk_aura",
    "animations": {
        "enabled": True,
        "waveform_bars": 24,
        "aura_pulse": True,
    },
    "layout": {
        "density": "balanced",  # balanced | compact | expanded
        "show_waveform": True,
        "show_feed": True,
    },
    "audio": {
        "input_device": "auto",
        "output_device": "auto",
        "mic_gain": 1.0,
        "sample_rate_in": 16000,
        "sample_rate_out": 24000,
    },
    "voice": {
        "stt_provider": "auto",        # auto | gemini_live | whisper | none
        "tts_provider": "system",      # system | piper | elevenlabs | none
        "voice_name": "en-gb",
        "auto_speak": False,
    },
    "wakeword": {
        "enabled": False,
        "provider": "openwakeword",
        "phrase": "hey dex",
        "threshold": 0.5,
        "cooldown_s": 2.0,
        "model_path": "providers/wakewords/hey_dex.onnx",
        "inference_framework": "onnx",
    },
    "ai": {
        "provider": "gemini",          # gemini | openai
        "gemini_model": "gemini-2.5-flash",
        "gemini_live_model": "gemini-2.5-flash-native-audio-preview-12-2025",
        "openai_base_url": "https://api.openai.com/v1",
        "openai_model": "gpt-4o-mini",
    },
    "shortcuts": {
        "settings": "s",
        "voice_primary": "ctrl+space",
        "voice_fallback": "ctrl+g",
    },
    "performance": {
        "tick_ms": 180,
        "telemetry_interval_s": 2.0,
        "background_scheduler": True,
    },
    "disabled_plugins": [],
    "disabled_actions": [],
    "approved_plugins": [],
    "boot_time": time.time(),
}


def _deep_merge(defaults: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(defaults)
    for k, v in existing.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = _deep_merge(merged[k], v)
        else:
            merged[k] = v
    return merged


def load_settings() -> dict[str, Any]:
    if SETTINGS_FILE.exists():
        try:
            raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                merged = _deep_merge(DEFAULT_SETTINGS, raw)
                if merged.get("active_suit") not in MARK_SUITS:
                    merged["active_suit"] = "mark57"
                if merged.get("theme") not in THEMES:
                    merged["theme"] = "cyberpunk_aura"
                return merged
        except Exception:
            pass
    return copy.deepcopy(DEFAULT_SETTINGS)


def save_settings(settings: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def load_api_keys() -> dict[str, str]:
    keys: dict[str, str] = {}
    if API_KEYS_FILE.exists():
        try:
            data = json.loads(API_KEYS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                keys = {str(k): str(v) for k, v in data.items() if v}
        except Exception:
            pass
    for env_key in ("GEMINI_API_KEY", "OPENAI_API_KEY", "ELEVENLABS_API_KEY"):
        env_val = os.environ.get(env_key, "").strip()
        if env_val and not keys.get(env_key):
            keys[env_key] = env_val
    return keys


def save_api_key(key_name: str, value: str) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    existing: dict[str, str] = {}
    if API_KEYS_FILE.exists():
        try:
            raw = json.loads(API_KEYS_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                existing = {str(k): str(v) for k, v in raw.items()}
        except Exception:
            pass
    if value.strip():
        existing[key_name] = value.strip()
    else:
        existing.pop(key_name, None)
    API_KEYS_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def mask_key(val: str) -> str:
    if not val:
        return "(not set)"
    if len(val) <= 8:
        return "****"
    return f"{val[:4]}...{val[-4:]}"


def export_config_backup(label: str = "manual") -> Path:
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_label = "".join(c for c in label if c.isalnum() or c in ("-", "_")) or "backup"
    target = BACKUPS_DIR / f"dex_config_{stamp}_{safe_label}.json"
    payload = {
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "settings": load_settings(),
    }
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target


def list_config_backups() -> list[Path]:
    if not BACKUPS_DIR.exists():
        return []
    return sorted(BACKUPS_DIR.glob("dex_config_*.json"), reverse=True)


def restore_config_backup(backup_path: Path) -> bool:
    if not backup_path.exists():
        return False
    try:
        data = json.loads(backup_path.read_text(encoding="utf-8"))
        settings = data.get("settings")
        if isinstance(settings, dict):
            merged = _deep_merge(DEFAULT_SETTINGS, settings)
            save_settings(merged)
            return True
    except Exception:
        pass
    return False
