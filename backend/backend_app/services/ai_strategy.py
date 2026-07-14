class AIReportStrategy:


    @staticmethod
    def should_generate(

        analysis,

        article_count

    ):


        print("========================")
        print(
            "AI生成判断:"
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
            "article_count:",
            article_count
        )

        print("========================")



        if analysis.risk_level == "高":

            return True



        if analysis.heat_score and analysis.heat_score >=80:

            return True



        if article_count >=5:

            return True



        return False