import sys
import types
import unittest
from unittest.mock import patch

if "app.services.kb_service" not in sys.modules:
    sys.modules["app.services.kb_service"] = types.ModuleType("app.services.kb_service")

from app.services import chat_service


class ChatBackgroundContextTests(unittest.TestCase):
    def test_generate_response_uses_background_context(self):
        chat = {"messages": []}
        intent_result = {"needs_kb": False, "target_file": None}

        with patch(
            "app.services.chat_service._build_background_context",
            return_value=(
                "[Background File: notes.md]\nimportant facts",
                [{"source": "notes.md", "page": 1}],
                ["f1"],
            ),
        ), patch(
            "app.services.chat_service.llm_service.answer_with_context",
            return_value="grounded answer",
        ):
            result = chat_service.generate_response(
                "p1",
                chat,
                "请根据背景资料回答",
                "GENERAL_CHAT",
                False,
                intent_result,
                ["f1"],
            )

        self.assertEqual(result["content"], "grounded answer")
        self.assertEqual(result["citations"], [{"source": "notes.md", "page": 1}])
        self.assertEqual(chat.get("background_file_ids"), ["f1"])

    def test_set_chat_background_files_filters_invalid_files(self):
        projects = {
            "p1": {
                "chats": {
                    "c1": {
                        "messages": [],
                        "background_file_ids": [],
                    }
                },
                "updated_at": "",
            }
        }

        def mock_get_file(project_id, file_id):
            mapping = {
                "f1": {"id": "f1", "name": "a.md", "type": "text", "content": "hello", "is_kb_file": False},
                "kb1": {"id": "kb1", "name": "b.pdf", "type": "pdf", "content": None, "is_kb_file": True},
                "img1": {"id": "img1", "name": "c.png", "type": "image", "content": None, "is_kb_file": False},
            }
            return mapping.get(file_id)

        with patch("app.services.chat_service.project_service.load_projects", return_value=projects), patch(
            "app.services.chat_service.project_service.save_projects"
        ) as save_projects, patch("app.services.chat_service.file_service.get_file", side_effect=mock_get_file):
            result = chat_service.set_chat_background_files("p1", "c1", ["f1", "kb1", "img1", "missing"])

        self.assertEqual(result["background_file_ids"], ["f1"])
        self.assertEqual(projects["p1"]["chats"]["c1"]["background_file_ids"], ["f1"])
        save_projects.assert_called_once()


if __name__ == "__main__":
    unittest.main()

