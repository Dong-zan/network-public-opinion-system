import unittest
from unittest.mock import patch

from fastapi import FastAPI
from pydantic import ValidationError

from backend_app.routers.ai import ask_ai, router
from backend_app.schemas.ai import AIAsk


class AIAskContractTests(unittest.TestCase):

    def test_openapi_exposes_event_id_and_question(self):

        app = FastAPI()
        app.include_router(router)

        openapi = app.openapi()
        request_schema = (
            openapi["paths"]["/api/ai/ask"]["post"]
            ["requestBody"]["content"]["application/json"]["schema"]
        )
        model_schema = openapi["components"]["schemas"]["AIAsk"]

        self.assertEqual(
            request_schema["$ref"],
            "#/components/schemas/AIAsk"
        )
        self.assertEqual(
            set(model_schema["required"]),
            {"event_id", "question"}
        )
        self.assertIn("event_id", model_schema["properties"])
        self.assertIn("question", model_schema["properties"])

    def test_model_rejects_invalid_event_id(self):

        with self.assertRaises(ValidationError):
            AIAsk(event_id=0, question="事件风险是什么？")

    def test_model_rejects_empty_question(self):

        with self.assertRaises(ValidationError):
            AIAsk(event_id=1, question="")

    @patch("backend_app.routers.ai.AIService")
    def test_route_keeps_existing_service_call(self, service_class):

        service_class.return_value.ask.return_value = {
            "answer": "测试回答"
        }

        response = ask_ai(
            AIAsk(event_id=1, question="事件风险是什么？"),
            object()
        )

        service_class.assert_called_once()
        service_class.return_value.ask.assert_called_once_with(
            1,
            "事件风险是什么？"
        )
        self.assertEqual(response["code"], 200)
        self.assertEqual(
            response["data"],
            {"answer": "测试回答"}
        )


if __name__ == "__main__":
    unittest.main()
