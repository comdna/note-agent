import sys
import types
import unittest
from unittest.mock import patch

# Stub heavy deps before importing chat_service.
if "app.services.kb_service" not in sys.modules:
    sys.modules["app.services.kb_service"] = types.ModuleType("app.services.kb_service")

from app.services import chat_service


class IntentDetectionTests(unittest.TestCase):
    def test_llm_label_generate_summary(self):
        with patch(
            "app.services.chat_service.llm_service.call_llm",
            return_value="GENERATE_SUMMARY",
        ) as call_llm:
            result = chat_service.analyze_intent_with_llm("帮我总结这个PDF")
        self.assertEqual(result["intent"], "GENERATE_SUMMARY")
        self.assertTrue(result["needs_kb"])
        call_llm.assert_called_once()

    def test_llm_label_search_kb_maps_to_query_kb(self):
        with patch(
            "app.services.chat_service.llm_service.call_llm",
            return_value="SEARCH_KB",
        ) as call_llm:
            result = chat_service.analyze_intent_with_llm("在资料里查一下这个概念")
        self.assertEqual(result["intent"], "QUERY_KB")
        self.assertTrue(result["needs_kb"])
        call_llm.assert_called_once()

    def test_llm_label_with_markdown_ticks(self):
        with patch(
            "app.services.chat_service.llm_service.call_llm",
            return_value="`WEB_SEARCH`",
        ):
            result = chat_service.analyze_intent_with_llm("搜一下最新新闻")
        self.assertEqual(result["intent"], "WEB_SEARCH")
        self.assertFalse(result["needs_kb"])

    def test_fallback_read_file_when_llm_fails(self):
        with patch(
            "app.services.chat_service.llm_service.call_llm",
            return_value="not-json",
        ):
            result = chat_service.analyze_intent_with_llm("read file.md")
        self.assertEqual(result["intent"], "READ_FILE")
        self.assertEqual(result["target_file"], "file.md")
        self.assertFalse(result["needs_kb"])

    def test_fallback_kb_query_keywords(self):
        with patch(
            "app.services.chat_service.llm_service.call_llm",
            return_value="not-json",
        ):
            result = chat_service.analyze_intent_with_llm("in the pdf, what is X?")
        self.assertEqual(result["intent"], "QUERY_KB")
        self.assertTrue(result["needs_kb"])

    def test_should_use_kb_respects_intent(self):
        with patch(
            "app.services.chat_service.llm_service.call_llm",
            return_value="SEARCH_KB",
        ):
            should_use = chat_service.should_use_knowledge_base("在文档里找定义")
        self.assertTrue(should_use)


if __name__ == "__main__":
    unittest.main()
