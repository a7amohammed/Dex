"""Centralized Gemini REST, multi-turn tool calling, and Gemini Live session bridge for DEX."""

from __future__ import annotations

import base64
import json
import threading
import urllib.error
import urllib.request
from typing import Any, Callable

from core.lazyimport import lazy_import
from memory.config_manager import load_api_keys, load_settings
from providers.audio import INPUT_RATE_HZ, OUTPUT_RATE_HZ, LinuxAudioCapture, play_pcm_audio
from providers.base import LiveEvent
from providers.schema import to_gemini_declaration


def get_gemini_api_key() -> str:
    return load_api_keys().get("GEMINI_API_KEY", "").strip()


def build_tool_declarations(dispatch_registry: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    run_tool = {
        "name": "run_terminal_tool",
        "description": (
            "Execute a registered DEX / Mark LVII terminal command (e.g. 'diag', 'status', "
            "'suit mark50', 'protocol house_party', 'task start <goal>', 'routine list', "
            "'remember <fact>', 'memory', 'pomodoro start 25', 'shop add <item>', 'water log 250', "
            "'py <code>', 'calc <expr>', 'scan', 'undo')."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "command": {"type": "STRING", "description": "Exact terminal command to invoke."},
            },
            "required": ["command"],
        },
    }
    decls = [to_gemini_declaration(run_tool)]
    for entry in dispatch_registry.values():
        tool = entry.get("tool")
        if isinstance(tool, dict) and tool.get("parameters"):
            decls.append(to_gemini_declaration(tool))
    return decls


def generate_chat_reply(
    prompt: str,
    system_prompt: str,
    history: list[dict[str, str]] | None = None,
    dispatch_fn: Callable[[str], dict[str, Any]] | None = None,
    tool_registry: dict[str, dict[str, Any]] | None = None,
) -> tuple[str, list[str]]:
    """Multi-turn Gemini REST call with optional tool dispatch; returns (reply_text, tool_traces)."""
    settings = load_settings()
    ai_cfg = settings.get("ai", {})
    provider_name = ai_cfg.get("provider", "gemini")

    if provider_name == "openai":
        from providers.registry import load_provider
        keys = load_api_keys()
        llm = load_provider(
            "openai",
            base_url=ai_cfg.get("openai_base_url", "https://api.openai.com/v1"),
            model=ai_cfg.get("openai_model", "gpt-4o-mini"),
            api_key=keys.get("OPENAI_API_KEY", ""),
        )
        msgs = [{"role": "system", "content": system_prompt}]
        for item in (history or [])[-8:]:
            msgs.append({"role": item["role"], "content": item["text"]})
        msgs.append({"role": "user", "content": prompt})
        try:
            ev = llm.generate(msgs)
            return ev.text or "No response returned.", []
        except Exception as exc:
            return f"OpenAI-compatible provider error: {exc}", []

    api_key = get_gemini_api_key()
    if not api_key:
        return (
            "GEMINI_API_KEY is not configured. Open Settings [S] -> AI Providers & Keys "
            "or export GEMINI_API_KEY in your shell. All local actions and plugins remain online.",
            [],
        )

    model = ai_cfg.get("gemini_model", "gemini-2.5-flash")
    contents: list[dict[str, Any]] = []
    for item in (history or [])[-8:]:
        role = "model" if item.get("role") in ("assistant", "dex", "model") else "user"
        contents.append({"role": role, "parts": [{"text": item.get("text", "")}]})
    contents.append({"role": "user", "parts": [{"text": prompt}]})

    payload: dict[str, Any] = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": contents,
    }
    if dispatch_fn is not None and tool_registry is not None:
        payload["tools"] = [{"functionDeclarations": build_tool_declarations(tool_registry)}]

    tool_traces: list[str] = []
    for _hop in range(2):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            return f"Gemini API error (HTTP {err.code}): {err.reason}", tool_traces
        except Exception as exc:
            return f"Gemini uplink error: {exc}", tool_traces

        cand_content = data.get("candidates", [{}])[0].get("content", {})
        parts = cand_content.get("parts", [])
        fn_calls = [p["functionCall"] for p in parts if "functionCall" in p]
        if fn_calls and dispatch_fn is not None:
            payload["contents"].append(cand_content)
            fn_responses: list[dict[str, Any]] = []
            for call in fn_calls:
                fname = call.get("name", "")
                args = call.get("args", {})
                cmd_str = str(args.get("command", fname)).strip()
                res = dispatch_fn(cmd_str)
                tool_traces.append(f"[TOOL {cmd_str}]")
                fn_responses.append({
                    "functionResponse": {
                        "name": fname,
                        "response": {"output": "\n".join(res.get("lines", [res.get("summary", "Done")]))},
                    }
                })
            payload["contents"].append({"role": "user", "parts": fn_responses})
            continue

        text = "".join(p.get("text", "") for p in parts).strip()
        return text or "Directive acknowledged.", tool_traces

    return "Tool execution completed.", tool_traces


class GeminiLiveVoiceSession:
    """Manages CTRL+SPACE voice listening via Linux audio capture + Gemini Live or STT->LLM->TTS fallback."""

    def __init__(
        self,
        dispatch_fn: Callable[[str], dict[str, Any]],
        system_prompt_fn: Callable[[], str],
        tool_registry: dict[str, dict[str, Any]],
        on_event: Callable[[LiveEvent], None],
        on_waveform: Callable[[list[int]], None],
    ) -> None:
        self.dispatch_fn = dispatch_fn
        self.system_prompt_fn = system_prompt_fn
        self.tool_registry = tool_registry
        self.on_event = on_event
        self.on_waveform = on_waveform

        self.listening = False
        self.state_label = "IDLE"
        self.wakeword_state = "OFF"
        self.last_wake_score = 0.0
        self.last_transcript = ""
        self.last_response = ""
        self._capture: LinuxAudioCapture | None = None
        self._wake_listener: Any = None
        self._worker: threading.Thread | None = None

    def arm_wakeword(self, on_wake: Callable[[float, str], None] | None = None) -> tuple[bool, str]:
        from providers.wakeword_oww import OpenWakeWordProvider, WakeWordListener

        settings = load_settings()
        ww_cfg = settings.get("wakeword", {})
        audio_cfg = settings.get("audio", {})
        if not ww_cfg.get("enabled", False):
            self.disarm_wakeword()
            return False, "Wake word ('hey dex') is disabled in settings."
        if self.listening:
            return False, "Voice session already listening."

        self.disarm_wakeword()
        provider = OpenWakeWordProvider(
            phrase=str(ww_cfg.get("phrase", "hey dex")),
            model_path=str(ww_cfg.get("model_path", "providers/wakewords/hey_dex.onnx")),
            threshold=float(ww_cfg.get("threshold", 0.5)),
            cooldown_s=float(ww_cfg.get("cooldown_s", 2.0)),
            inference_framework=str(ww_cfg.get("inference_framework", "onnx")),
        )

        def _detected(score: float, label: str) -> None:
            self.last_wake_score = score
            self.wakeword_state = f"TRIGGERED ({score:.2f})"
            self.on_event(LiveEvent(kind="text", text=f"Wake word '{provider.phrase}' detected ({score:.2f})"))
            if on_wake is not None:
                on_wake(score, label)
            else:
                self.start_listening()

        def _status(msg: str) -> None:
            self.wakeword_state = self._wake_listener.state_label if self._wake_listener else "OFF"
            self.on_event(LiveEvent(kind="text", text=msg))

        self._wake_listener = WakeWordListener(
            provider=provider,
            on_detected=_detected,
            on_status=_status,
            device=str(audio_cfg.get("input_device", "auto")),
            gain=float(audio_cfg.get("mic_gain", 1.0)),
        )
        ok, msg = self._wake_listener.start()
        self.wakeword_state = self._wake_listener.state_label
        return ok, msg

    def disarm_wakeword(self) -> None:
        if self._wake_listener is not None:
            self._wake_listener.stop()
            self._wake_listener = None
        self.wakeword_state = "OFF"

    def start_listening(self) -> tuple[bool, str]:
        if self.listening:
            return True, "Already listening."

        self.disarm_wakeword()
        settings = load_settings()
        audio_cfg = settings.get("audio", {})
        self._capture = LinuxAudioCapture(
            device=audio_cfg.get("input_device", "auto"),
            gain=float(audio_cfg.get("mic_gain", 1.0)),
        )
        ok, msg = self._capture.start(on_chunk=lambda _raw, bars: self.on_waveform(bars))
        if not ok:
            self.state_label = "MIC UNAVAILABLE"
            self.on_event(LiveEvent(kind="error", text=msg))
            return False, msg

        self.listening = True
        self.state_label = "LISTENING"
        self.on_event(LiveEvent(kind="text", text=f"Voice listening started ({msg})"))
        return True, msg

    def stop_and_process(self) -> None:
        if not self.listening or self._capture is None:
            return
        self.listening = False
        self.state_label = "PROCESSING"
        pcm = self._capture.stop()
        self.on_waveform([0] * 24)

        def _process() -> None:
            try:
                api_key = get_gemini_api_key()
                websockets = lazy_import("websockets")
                if api_key and websockets is not None and pcm:
                    live_ok, live_msg = self._try_gemini_live_ws(api_key, pcm)
                    if live_ok:
                        self.state_label = "IDLE"
                        self.on_event(LiveEvent(kind="done", text=live_msg))
                        return

                # Fallback: Whisper STT -> Gemini/OpenAI LLM -> System/Piper/ElevenLabs TTS
                from providers.registry import load_provider
                settings = load_settings()
                voice_cfg = settings.get("voice", {})
                keys = load_api_keys()
                stt = load_provider("whisper", api_key=keys.get("OPENAI_API_KEY", ""))
                tts_name = voice_cfg.get("tts_provider", "system")
                tts = None
                if tts_name == "piper":
                    tts = load_provider("tts_piper")
                elif tts_name == "elevenlabs":
                    tts = load_provider("tts_elevenlabs", api_key=keys.get("ELEVENLABS_API_KEY", ""))
                elif tts_name == "system":
                    tts = load_provider("tts_system", voice=voice_cfg.get("voice_name", "en-gb"))

                if not stt.is_available():
                    self.state_label = "STT MISSING"
                    self.on_event(
                        LiveEvent(
                            kind="error",
                            text=(
                                "Captured audio frames, but neither Gemini Live (`websockets` + `GEMINI_API_KEY`) "
                                "nor STT (`faster-whisper` / `OPENAI_API_KEY`) is available."
                            ),
                        )
                    )
                    return

                ok_stt, transcript = stt.transcribe(pcm, INPUT_RATE_HZ)
                if not ok_stt:
                    self.state_label = "IDLE"
                    self.on_event(LiveEvent(kind="error", text=transcript))
                    return

                self.last_transcript = transcript
                self.on_event(LiveEvent(kind="text", text=f"TRANSCRIPT: {transcript}"))
                self.state_label = "RESPONDING"

                reply, _traces = generate_chat_reply(
                    transcript,
                    self.system_prompt_fn(),
                    dispatch_fn=self.dispatch_fn,
                    tool_registry=self.tool_registry,
                )
                self.last_response = reply
                self.on_event(LiveEvent(kind="text", text=f"DEX: {reply}"))

                if tts is not None and tts.is_available():
                    tts.speak(reply)
                self.state_label = "IDLE"
                self.on_event(LiveEvent(kind="done"))
            except Exception as exc:
                self.state_label = "ERROR"
                self.on_event(LiveEvent(kind="error", text=f"Voice pipeline error: {exc}"))

        self._worker = threading.Thread(target=_process, daemon=True)
        self._worker.start()

    def _try_gemini_live_ws(self, api_key: str, pcm: bytes) -> tuple[bool, str]:
        """Stream captured PCM16 to Gemini Live BidiGenerateContent WebSocket when websockets is installed."""
        import asyncio
        ws_mod = lazy_import("websockets")
        if ws_mod is None:
            return False, "websockets package not installed."

        settings = load_settings()
        live_model = settings.get("ai", {}).get("gemini_live_model", "gemini-2.5-flash-native-audio-preview-12-2025")
        uri = f"wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key={api_key}"

        async def _session() -> str:
            audio_out = bytearray()
            text_out: list[str] = []
            async with ws_mod.connect(uri, open_timeout=10) as ws:
                setup_msg = {
                    "setup": {
                        "model": f"models/{live_model}",
                        "generationConfig": {"responseModalities": ["AUDIO", "TEXT"]},
                        "systemInstruction": {"parts": [{"text": self.system_prompt_fn()}]},
                    }
                }
                await ws.send(json.dumps(setup_msg))
                await ws.recv()  # setupComplete

                await ws.send(json.dumps({
                    "realtimeInput": {
                        "mediaChunks": [{
                            "mimeType": f"audio/pcm;rate={INPUT_RATE_HZ}",
                            "data": base64.b64encode(pcm).decode("ascii"),
                        }]
                    }
                }))
                await ws.send(json.dumps({"clientContent": {"turnComplete": True}}))

                while True:
                    raw_msg = await asyncio.wait_for(ws.recv(), timeout=15)
                    msg = json.loads(raw_msg)
                    sc = msg.get("serverContent")
                    if not sc:
                        continue
                    for part in sc.get("modelTurn", {}).get("parts", []):
                        if "text" in part:
                            text_out.append(part["text"])
                        if "inlineData" in part:
                            b64 = part["inlineData"].get("data", "")
                            if b64:
                                audio_out.extend(base64.b64decode(b64))
                    if sc.get("turnComplete"):
                        break

            if audio_out:
                play_pcm_audio(bytes(audio_out), OUTPUT_RATE_HZ)
            reply = "".join(text_out).strip() or "Gemini Live audio response played."
            self.last_response = reply
            self.on_event(LiveEvent(kind="text", text=f"DEX (Live): {reply}"))
            return reply

        try:
            return True, asyncio.run(_session())
        except Exception as exc:
            return False, f"Gemini Live WebSocket fallback: {exc}"
