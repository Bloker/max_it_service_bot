import unittest

from app.helpdesk.services.user_flow_service import UserFlowService


class UserFlowServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = UserFlowService()

    def test_begin_create_resets_text_and_attachments(self) -> None:
        user_id = 101
        self.service.begin_create(user_id)
        self.service.append_problem_chunk(user_id, text="first", attachments=["a1"])

        draft = self.service.begin_create(user_id)
        self.assertEqual("awaiting_category", draft.step)
        self.assertIsNone(draft.category)
        self.assertIsNone(draft.problem_text)
        self.assertEqual([], draft.attachments)

    def test_append_problem_chunk_accumulates_text_and_attachments(self) -> None:
        user_id = 202
        self.service.begin_create(user_id)
        self.service.set_category(user_id, "VPN")

        draft = self.service.append_problem_chunk(user_id, text="line 1", attachments=["img1"])
        draft = self.service.append_problem_chunk(user_id, text="line 2", attachments=["img2"])

        self.assertEqual("line 1\nline 2", draft.problem_text)
        self.assertEqual(["img1", "img2"], draft.attachments)


if __name__ == "__main__":
    unittest.main()
