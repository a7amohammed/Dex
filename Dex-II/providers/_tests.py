"""Offline self-tests for Mark LVII providers (`python3 -m providers._tests`)."""

from __future__ import annotations

import unittest

from providers.base import LiveEvent, ProviderCapabilities
from providers.registry import list_available_providers, load_provider
from providers.schema import to_anthropic_tool, to_gemini_declaration, to_openai_tool


class ProviderTests(unittest.TestCase):
    def test_schema_conversion(self) -> None:
        sample = {
            "name": "deploy_suit",
            "description": "Switch active Mark chassis",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "mark": {"type": "STRING", "description": "Mark identifier"},
                },
                "required": ["mark"],
            },
        }
        g = to_gemini_declaration(sample)
        o = to_openai_tool(sample)
        a = to_anthropic_tool(sample)
        self.assertEqual(g["parameters"]["type"], "OBJECT")
        self.assertEqual(o["function"]["parameters"]["type"], "object")
        self.assertEqual(a["input_schema"]["properties"]["mark"]["type"], "string")

    def test_registry_and_capabilities(self) -> None:
        providers = list_available_providers()
        self.assertIn("gemini", providers)
        self.assertIn("openai", providers)
        self.assertIn("openwakeword", providers)
        llm = load_provider("openai", model="local-model")
        self.assertTrue(llm.capabilities.tool_calling)
        ev = LiveEvent(kind="text", text="Nominal")
        self.assertEqual(ev.text, "Nominal")
        caps = ProviderCapabilities()
        self.assertEqual((caps.audio_in_hz, caps.audio_out_hz), (16000, 24000))


def run_suite() -> tuple[bool, str]:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ProviderTests)
    import io
    buf = io.StringIO()
    runner = unittest.TextTestRunner(stream=buf, verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful(), buf.getvalue()


if __name__ == "__main__":
    ok, output = run_suite()
    print(output)
    raise SystemExit(0 if ok else 1)
