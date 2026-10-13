import json
import unittest

from backend.ai.provider import ProviderParseError, parse_provider_response_json


class ProviderResponseParserTests(unittest.TestCase):
    def test_parses_chat_completions_shape(self) -> None:
        response = {
            "choices": [
                {
                    "message": {
                        "content": '{"status":"ok"}',
                    }
                }
            ]
        }

        parsed = parse_provider_response_json(response)

        self.assertEqual(parsed.parsed_json, {"status": "ok"})
        self.assertEqual(parsed.normalized.source_format, "chat_completions")

    def test_parses_ollama_response_shape(self) -> None:
        response = {"response": '{"domain":"utility","features":["Fault Monitoring"]}'}

        parsed = parse_provider_response_json(response)

        self.assertEqual(parsed.parsed_json["domain"], "utility")
        self.assertEqual(parsed.normalized.source_format, "ollama_response")

    def test_parses_plain_text_with_embedded_json(self) -> None:
        response = 'Here is the result:\n{"status":"ok","confidence":"high"}'

        parsed = parse_provider_response_json(response)

        self.assertEqual(parsed.parsed_json["status"], "ok")
        self.assertEqual(parsed.parsed_json["confidence"], "high")

    def test_parses_json_string_response(self) -> None:
        response = '{"status":"ok","items":[1,2]}'

        parsed = parse_provider_response_json(response)

        self.assertEqual(parsed.parsed_json["items"], [1, 2])
        self.assertEqual(parsed.normalized.source_format, "json_string")

    def test_parses_markdown_fenced_json(self) -> None:
        response = "```json\n{\"status\":\"ok\"}\n```"

        parsed = parse_provider_response_json(response)

        self.assertEqual(parsed.parsed_json, {"status": "ok"})

    def test_repairs_trailing_commas(self) -> None:
        response = '{"status":"ok","items":["a","b",],}'

        parsed = parse_provider_response_json(response)

        self.assertEqual(parsed.parsed_json["items"], ["a", "b"])

    def test_parses_python_like_dict_response(self) -> None:
        response = "{'status': 'ok', 'answered': True, 'notes': None}"

        parsed = parse_provider_response_json(response)

        self.assertEqual(parsed.parsed_json["status"], "ok")
        self.assertTrue(parsed.parsed_json["answered"])
        self.assertIsNone(parsed.parsed_json["notes"])

    def test_rejects_non_json_plain_text(self) -> None:
        with self.assertRaises(ProviderParseError) as ctx:
            parse_provider_response_json("I cannot return JSON right now.")

        self.assertEqual(ctx.exception.code, "NoJsonObjectFound")

    def test_rejects_non_object_json(self) -> None:
        with self.assertRaises(ProviderParseError) as ctx:
            parse_provider_response_json(json.dumps(["not", "an", "object"]))

        self.assertEqual(ctx.exception.code, "NonDictParsedJson")


if __name__ == "__main__":
    unittest.main()
