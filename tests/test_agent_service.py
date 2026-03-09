import unittest
from unittest.mock import patch

from app.services import agent_service


class AgentServiceTests(unittest.TestCase):
    def setUp(self):
        agent_service._graph = None

    def test_list_files_tool(self):
        with patch("app.services.agent_service.file_service.list_files") as list_files:
            list_files.return_value = [
                {"id": "a1", "name": "notes.md"},
                {"id": "b2", "name": "todo.txt"},
            ]
            result = agent_service._tool_execute(
                "proj1",
                "what files are uploaded?",
                {"tool_name": "list_files", "tool_args": {}},
            )

        self.assertIsNotNone(result)
        self.assertIn("notes.md", result["content"])
        self.assertIn("todo.txt", result["content"])
        self.assertEqual(result["steps"][0]["tool"], "list_files")

    def test_read_file_tool(self):
        with patch("app.services.agent_service.file_service.list_files") as list_files, patch(
            "app.services.agent_service.file_service.get_file"
        ) as get_file, patch("app.services.agent_service.llm_service.call_llm") as call_llm:
            list_files.return_value = [{"id": "a1", "name": "notes.md"}]
            get_file.return_value = {
                "id": "a1",
                "name": "notes.md",
                "content": "hello world",
            }
            call_llm.return_value = "file-based answer"

            result = agent_service._tool_execute(
                "proj1",
                "read notes.md",
                {"tool_name": "read_file", "tool_args": {"name_or_id": "notes.md"}},
            )

        self.assertIsNotNone(result)
        self.assertEqual(result["content"], "file-based answer")
        self.assertEqual(result["citations"][0]["source"], "notes.md")

    def test_update_file_tool(self):
        with patch("app.services.agent_service.file_service.update_file") as update_file:
            update_file.return_value = {"id": "a1", "name": "notes.md", "content": "updated"}

            result = agent_service._tool_execute(
                "proj1",
                "update file",
                {
                    "tool_name": "update_file",
                    "tool_args": {"file_id": "a1", "content": "updated"},
                },
            )

        self.assertIsNotNone(result)
        self.assertIn("updated", result["content"].lower())
        self.assertEqual(result["steps"][0]["tool"], "update_file")

    def test_delete_file_tool(self):
        with patch("app.services.agent_service.file_service.delete_file") as delete_file:
            delete_file.return_value = (True, None)

            result = agent_service._tool_execute(
                "proj1",
                "delete file",
                {"tool_name": "delete_file", "tool_args": {"file_id": "a1"}},
            )

        self.assertIsNotNone(result)
        self.assertEqual(result["content"], "File deleted.")
        self.assertEqual(result["steps"][0]["tool"], "delete_file")

    def test_list_kb_files_tool(self):
        with patch("app.services.agent_service.file_service.list_kb_files") as list_kb_files:
            list_kb_files.return_value = [
                {"id": "k1", "name": "doc-a.pdf"},
                {"id": "k2", "name": "doc-b.pdf"},
            ]

            result = agent_service._tool_execute(
                "proj1",
                "list kb files",
                {"tool_name": "list_kb_files", "tool_args": {}},
            )

        self.assertIsNotNone(result)
        self.assertIn("doc-a.pdf", result["content"])
        self.assertIn("doc-b.pdf", result["content"])
        self.assertEqual(result["steps"][0]["tool"], "list_kb_files")

    def test_search_kb_tool(self):
        with patch("app.services.agent_service.kb_service.search_kb") as search_kb, patch(
            "app.services.agent_service.llm_service.answer_with_context"
        ) as answer_with_context:
            search_kb.return_value = [
                {"source": "doc.pdf", "page": 1, "score": 0.9, "text": "x is ..."},
                {"source": "doc.pdf", "page": 2, "score": 0.8, "text": "more x ..."},
            ]
            answer_with_context.return_value = "answer from kb"

            result = agent_service._tool_execute(
                "proj1",
                "what is x?",
                {
                    "tool_name": "search_kb",
                    "tool_args": {"query": "what is x", "top_k": 2},
                },
            )

        self.assertIsNotNone(result)
        self.assertEqual(result["content"], "answer from kb")
        self.assertTrue(result["used_kb"])
        self.assertEqual(result["steps"][0]["tool"], "search_kb")

    def test_web_search_tool(self):
        with patch("app.services.agent_service._search_web") as search_web, patch(
            "app.services.agent_service.llm_service.answer_with_context"
        ) as answer_with_context:
            search_web.return_value = (
                [
                    {
                        "title": "Latest AI News",
                        "link": "https://example.com/news",
                        "snippet": "Top updates today",
                        "position": 1,
                    }
                ],
                None,
            )
            answer_with_context.return_value = "web-based answer"

            result = agent_service._tool_execute(
                "proj1",
                "search the web",
                {"tool_name": "web_search", "tool_args": {"query": "latest news"}},
            )

        self.assertIsNotNone(result)
        self.assertEqual(result["content"], "web-based answer")
        self.assertEqual(result["citations"][0]["source"], "Latest AI News")
        self.assertEqual(result["steps"][0]["tool"], "web_search")

    def test_search_web_requires_serpapi_key(self):
        with patch("app.services.agent_service.SERPAPI_KEY", None):
            results, error = agent_service._search_web("latest news")

        self.assertIsNone(results)
        self.assertIn("SERPAPI_KEY", error)

    def test_run_tool_call_supports_multi_round(self):
        with patch("app.services.agent_service.decide_tool") as decide_tool, patch(
            "app.services.agent_service._tool_execute"
        ) as tool_execute:
            decide_tool.side_effect = [
                {"action": "tool", "tool_name": "list_files", "tool_args": {}},
                {"action": "final", "response": "已完成，两步信息已整合"},
            ]
            tool_execute.return_value = {
                "content": "Uploaded files:\n- notes.md",
                "citations": [],
                "used_kb": False,
                "steps": [
                    {
                        "type": "tool_call",
                        "tool": "list_files",
                        "args": {},
                        "result": "Uploaded files: - notes.md",
                    }
                ],
            }

            result = agent_service.run_tool_call("proj1", "先列文件再给我结论")

        self.assertEqual(result["content"], "已完成，两步信息已整合")
        self.assertEqual(len(result["steps"]), 1)
        self.assertEqual(result["steps"][0]["tool"], "list_files")

    def test_run_tool_call_respects_round_limit(self):
        with patch("app.services.agent_service.decide_tool") as decide_tool, patch(
            "app.services.agent_service._tool_execute"
        ) as tool_execute:
            decide_tool.return_value = {"action": "tool", "tool_name": "list_files", "tool_args": {}}
            tool_execute.return_value = {
                "content": "Uploaded files:\n- notes.md",
                "citations": [],
                "used_kb": False,
                "steps": [
                    {
                        "type": "tool_call",
                        "tool": "list_files",
                        "args": {},
                        "result": "Uploaded files: - notes.md",
                    }
                ],
            }

            result = agent_service.run_tool_call("proj1", "重复执行")

        self.assertIsNotNone(result)
        self.assertEqual(tool_execute.call_count, agent_service.MAX_TOOL_ROUNDS)
        self.assertEqual(len(result["steps"]), agent_service.MAX_TOOL_ROUNDS)


if __name__ == "__main__":
    unittest.main()
