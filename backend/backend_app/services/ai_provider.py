import requests
import os

from abc import ABC, abstractmethod
from backend_app.config import settings


class AIProviderError(RuntimeError):
    """An AI service failure that the backend can expose as an HTTP error."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


class AIProvider(ABC):


    @abstractmethod
    def ask(self, context: dict):
        pass


    @abstractmethod
    def report(self, context: dict):
        pass


    @abstractmethod
    def verify(self, context: dict):
        pass


class RealAIProvider(AIProvider):


    BASE_URL = settings.AI_SERVER_URL



    def ask(self, context: dict):


        try:

            response = requests.post(
                f"{self.BASE_URL}/ai/ask",
                json=context,
                timeout=60
            )


            response.raise_for_status()


            return response.json()


        except requests.exceptions.RequestException as e:


            return {

                "error": True,

                "message": str(e)

            }




    def report(self, context: dict):


        try:


            print("====================")
            print("SEND TO AI REPORT")
            print(context)
            print("====================")



            response = requests.post(

                f"{self.BASE_URL}/ai/report",

                json=context,

                timeout=120

            )



            print("AI STATUS:",response.status_code)

            print(
                "AI RESPONSE:",
                response.text
            )



            response.raise_for_status()



            return response.json()



        except requests.exceptions.HTTPError as e:



            return {


                "error": True,


                "status":

                e.response.status_code,


                "message":

                e.response.text


            }



        except requests.exceptions.RequestException as e:



            return {


                "error": True,


                "message":str(e)


            }




    def verify(self, context:dict):


        try:


            response=requests.post(

                f"{self.BASE_URL}/ai/verify",

                json=context,

                timeout=60

            )

        except requests.exceptions.Timeout as exc:
            raise AIProviderError(
                503,
                "AI service request timed out"
            ) from exc

        except requests.exceptions.ConnectionError as exc:
            raise AIProviderError(
                503,
                "AI service is unavailable"
            ) from exc

        except requests.exceptions.RequestException as exc:
            raise AIProviderError(
                503,
                "AI service is unavailable"
            ) from exc


        if response.status_code >= 400:
            if response.status_code in {404, 422}:
                status_code = response.status_code
                message = self._error_message(response)
            else:
                status_code = 503
                message = "AI service is unavailable"

            raise AIProviderError(
                status_code,
                message
            )


        try:
            result = response.json()
        except ValueError as exc:
            raise AIProviderError(
                503,
                "AI service returned invalid JSON"
            ) from exc


        if not isinstance(result, dict):
            raise AIProviderError(
                503,
                "AI service response must be a JSON object"
            )


        return result


    @staticmethod
    def _error_message(response) -> str:
        try:
            body = response.json()
        except ValueError:
            body = None

        if isinstance(body, dict):
            detail = body.get("detail") or body.get("message")
            if isinstance(detail, str) and detail.strip():
                return detail
            if detail:
                return str(detail)

        text = getattr(response, "text", "").strip()
        return text or f"AI service returned HTTP {response.status_code}"



class FakeAIProvider(AIProvider):



    def ask(
        self,
        context:dict
    ):



        question=context.get(
            "question",
            ""
        )



        return {


            "answer":

            f"这是测试AI回答：{question}",



            "summary":

            "基于当前事件数据生成的测试摘要",



            "trend":

            "事件热度正在变化",



            "risk":

            "需要持续关注",



            "suggestion":

            "建议结合更多数据判断"


        }



    def report(self,context:dict):


        return {


            "overview":{


                "title":

                context["event"]["title"]


            },


            "summary":

            "测试报告摘要",



            "trend_analysis":

            "测试趋势分析",



            "risk_analysis":

            "测试风险分析",



            "suggestions":[

                "持续关注事件发展"

            ],



            "limitations":[]


        }



    def verify(self,context:dict):


        return {


            "verified":

            True

        }
