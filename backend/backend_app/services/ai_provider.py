from abc import ABC, abstractmethod



class AIProvider(ABC):


    @abstractmethod
    def ask(
        self,
        context:dict
    ):

        pass




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