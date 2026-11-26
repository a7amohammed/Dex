# openWakeWord Models (`hey dex`)

Place your trained **openWakeWord** model for `"hey dex"` in this folder as:

- `hey_dex.onnx` (recommended — ONNX Runtime)
- or `hey_dex.tflite` (set `"inference_framework": "tflite"` in Settings `[S]` -> `Voice Preferences`)

Optional Python dependencies:

```bash
pip install openwakeword onnxruntime numpy
```

Once installed and placed here, enable **Wake Word ("hey dex")** in Settings `[S]` -> `Voice Preferences` or press `[W]` inside the Voice Panel (`Ctrl+Space` / `Ctrl+G`).
