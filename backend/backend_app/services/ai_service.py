from sqlalchemy.orm import Session
from datetime import datetime
import json

from pydantic import ValidationError


from backend_app.models.event import Event
from backend_app.models.article import Article
from backend_app.models.analysis import Analysis
from backend_app.models.ai_result import AIResult
from backend_app.schemas.ai import AIVerifyResult
from backend_app.services.ai_provider import AIProviderError, RealAIProvider


class AIResourceNotFoundError(RuntimeError):
    status_code = 404

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)



class AIService:


    def __init__(
        self,
        db: Session
    ):

        self.db = db
        self.provider = RealAIProvider()



    # =====================================================
    # 构建发送给AI的数据
    # =====================================================

    def build_context(
        self,
        event_id:int
    ):


        print(
            "[AI] build_context event_id:",
            event_id
        )


        event = self.db.query(
            Event
        ).filter(
            Event.event_id == event_id
        ).first()



        if not event:

            raise AIResourceNotFoundError(
                f"event {event_id} not found"
            )



        articles = self.db.query(
            Article
        ).filter(
            Article.event_id == event_id
        ).all()



        analyses = self.db.query(
            Analysis
        ).filter(
            Analysis.event_id == event_id
        ).all()



        keywords = []



        for item in analyses:


            if item.keywords:


                try:


                    if isinstance(
                        item.keywords,
                        str
                    ):


                        data = json.loads(
                            item.keywords
                        )


                        if isinstance(
                            data,
                            list
                        ):

                            keywords.extend(
                                data
                            )


                    elif isinstance(
                        item.keywords,
                        list
                    ):


                        keywords.extend(
                            item.keywords
                        )


                except Exception as e:


                    print(
                        "[AI]关键词解析失败:",
                        e
                    )





        # ==========================================
        # 情绪比例计算
        # ==========================================


        analysis_count = len(
            analyses
        ) or 1



        positive = sum(

            x.positive or 0

            for x in analyses

        ) / analysis_count




        neutral = sum(

            x.neutral or 0

            for x in analyses

        ) / analysis_count




        negative = sum(

            x.negative or 0

            for x in analyses

        ) / analysis_count

        return {


            "event":{


                "event_id":

                    event.event_id,



                "title":

                    event.title or "",



                "summary":

                    event.summary or "",



                "update_time":

                    str(
                        event.update_time
                    )
                    if event.update_time
                    else None,




                "articles":[



                    {


                        "news_id":

                            article.news_id,



                        "title":

                            article.title or "",



                        "content":

                            article.content or "",



                        "source":

                            article.source or "",



                        "url":

                            article.url or "",



                        "publish_time":

                            str(
                                article.publish_time
                            )
                            if article.publish_time
                            else "",



                        "platform":

                            article.platform or "",



                        "author":

                            article.author or None,



                        "account_type":

                            article.account_type or None,



                        "is_official":

                            article.is_official,



                        "reference_urls":

                            article.reference_urls
                            if isinstance(article.reference_urls, list)
                            else [],



                        "quoted_news_ids":

                            article.quoted_news_ids
                            if isinstance(article.quoted_news_ids, list)
                            else [],



                        "duplicate_group_id":

                            article.duplicate_group_id or None

                    }


                    for article in articles


                ],




                "analysis":{


                    "keywords":

                        keywords,



                    "sentiment":{


                        "positive":

                            round(
                                positive,
                                4
                            ),



                        "neutral":

                            round(
                                neutral,
                                4
                            ),



                        "negative":

                            round(
                                negative,
                                4
                            )

                    },



                    "heat":

                        event.heat or 0,



                    "stage":

                        event.stage or "",



                    "risk_level":

                        event.risk_level or ""

                }


            }

        }






    # =====================================================
    # 用户问答
    # =====================================================


    def ask(
        self,
        event_id:int,
        question:str
    ):


        context = self.build_context(
            event_id
        )


        context["question"] = question



        return self.provider.ask(
            context
        )





    # =====================================================
    # 新闻真实性核验
    # =====================================================


    def verify(
        self,
        event_id:int,
        news_id:int,
        max_claims:int = 5
    ):


        print(
            "[AI]进入 verify"
        )



        context = self.build_context(
            event_id
        )



        context["target_news_id"] = news_id


        context["max_claims"] = max_claims




        print(
            "========== AI VERIFY REQUEST =========="
        )


        print(
            context
        )


        print(
            "========================================"
        )




        result = self.provider.verify(
            context
        )



        print(
            "========== AI VERIFY RESPONSE =========="
        )


        print(
            result
        )


        print(
            "========================================"
        )



        return self._normalize_verify_result(
            result,
            event_id=event_id,
            news_id=news_id,
        )

    # =====================================================
    # 保存真实性结果
    # =====================================================

    def save_verify_result(
        self,
        event_id:int,
        news_id:int,
        max_claims:int = 5
    ):


        result = self.verify(
            event_id,
            news_id,
            max_claims
        )


        ai = self.db.query(
            AIResult
        ).filter(
            AIResult.event_id == event_id
        ).first()



        if not ai:


            print(
                "[AI]创建真实性结果记录"
            )


            ai = AIResult(

                event_id=event_id,

                generated_at=datetime.now(),

                provider="real_ai",

                status="success"

            )


            self.db.add(ai)



        ai.authenticity = result


        ai.generated_at = datetime.now()


        ai.provider = "real_ai"


        ai.status = "success"


        ai.error_message = None



        self.db.commit()


        self.db.refresh(
            ai
        )



        print(
            "[AI]真实性结果保存成功"
        )


        return result

    @staticmethod
    def _normalize_verify_result(
        result,
        *,
        event_id: int,
        news_id: int,
    ) -> dict:
        if not isinstance(result, dict):
            raise AIProviderError(
                503,
                "AI service returned an incompatible verification response",
            )

        payload = dict(result)
        upstream_event_id = payload.get("event_id")
        if upstream_event_id is not None and str(upstream_event_id) != str(event_id):
            raise AIProviderError(
                503,
                "AI service returned a mismatched event_id",
            )
        upstream_target_news_id = payload.get("target_news_id")
        if (
            upstream_target_news_id is not None
            and str(upstream_target_news_id) != str(news_id)
        ):
            raise AIProviderError(
                503,
                "AI service returned a mismatched target_news_id",
            )

        # event_id/news_id are trusted routing identifiers already known by the
        # backend.  Adding them here keeps the frontend contract stable while
        # remaining compatible with an older AI process during a rolling restart.
        payload["event_id"] = event_id
        payload["news_id"] = news_id

        try:
            validated = AIVerifyResult.model_validate(payload)
        except ValidationError as exc:
            raise AIProviderError(
                503,
                "AI service returned an incompatible verification response",
            ) from exc
        return validated.model_dump(mode="json")





    # =====================================================
    # 生成AI报告
    # =====================================================

    def generate_report(
        self,
        event_id:int
    ):


        print(
            "[AI]进入 generate_report"
        )


        context = self.build_context(
            event_id
        )


        print(
            "========== AI REQUEST =========="
        )

        print(
            "event_id:",
            event_id
        )


        print(
            "article count:",
            len(
                context["event"]["articles"]
            )
        )


        print(
            "================================"
        )



        result = self.provider.report(
            context
        )



        print(
            "========== AI RESPONSE =========="
        )


        print(
            result
        )


        print(
            "================================="
        )



        if not isinstance(
            result,
            dict
        ):

            raise Exception(
                f"AI返回格式错误:{result}"
            )



        error_value = result.get(
            "error"
        )


        failed = False

        error_message = None



        if (

            error_value is True

            or error_value == 1

            or str(error_value).lower() == "true"

        ):


            failed = True


            error_message = result.get(
                "message",
                "AI调用失败"
            )


            print(
                "[AI]调用失败:",
                error_message
            )



        else:


            if "data" in result:


                result = result["data"]




        ai = self.db.query(
            AIResult
        ).filter(
            AIResult.event_id == event_id
        ).first()



        if not ai:


            print(
                "[AI]创建AIResult"
            )


            ai = AIResult(

                event_id=event_id,

                generated_at=datetime.now(),

                provider="real_ai"

            )


            self.db.add(ai)




        # ===============================
        # AI失败保存
        # ===============================

        if failed:


            ai.status = "failed"


            ai.error_message = error_message


            ai.ai_report = {


                "error": True,


                "message": error_message

            }




        # ===============================
        # AI成功保存
        # ===============================

        else:


            ai.status = "success"


            ai.error_message = None



            ai.ai_report = {


                "summary":

                    result.get(
                        "summary",
                        ""
                    ),



                "overview":

                    result.get(
                        "overview",
                        {}
                    ),



                "trend_analysis":

                    result.get(
                        "trend_analysis",
                        ""
                    ),



                "risk_analysis":

                    result.get(
                        "risk_analysis",
                        ""
                    ),



                "suggestions":

                    result.get(
                        "suggestions",
                        []
                    ),



                "limitations":

                    result.get(
                        "limitations",
                        []
                    )

            }




        self.db.commit()



        self.db.refresh(
            ai
        )



        print(
            "[AI]报告保存完成",
            event_id,
            ai.status
        )



        return ai







    # =====================================================
    # 判断是否需要生成报告
    # =====================================================

    def try_generate_report(
        self,
        event_id:int
    ):


        print(
            "[AI]进入 try_generate_report",
            event_id
        )



        event = self.db.query(
            Event
        ).filter(
            Event.event_id == event_id
        ).first()



        if not event:


            raise Exception(
                f"event {event_id} not found"
            )




        article_count = self.db.query(
            Article
        ).filter(
            Article.event_id == event_id
        ).count()



        print(
            "[AI]文章数量:",
            article_count
        )




        analysis = self.db.query(
            Analysis
        ).filter(
            Analysis.event_id == event_id
        ).first()



        if not analysis:


            print(
                "[AI]没有analysis，不生成"
            )


            return None





        print(
            "========== AI生成判断 =========="
        )


        print(
            "risk:",
            analysis.risk_level
        )


        print(
            "heat:",
            analysis.heat_score
        )


        print(
            "articles:",
            article_count
        )


        print(
            "================================"
        )




        need_generate = False




        if analysis.risk_level == "高":


            need_generate = True



        elif (

            analysis.heat_score

            and analysis.heat_score >= 80

        ):


            need_generate = True



        elif article_count >= 3:


            need_generate = True





        print(
            "[AI]是否生成:",
            need_generate
        )




        if not need_generate:


            print(
                "[AI]暂不生成报告"
            )


            return None





        return self.generate_report(
            event_id
        )
