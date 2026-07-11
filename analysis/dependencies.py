"""Required third-party dependency checks for the analysis module."""

from importlib import import_module


class AnalysisDependencyError(RuntimeError):
    """Raised when the analysis module cannot run because dependencies are missing."""


_CHECKED = False


def check_required_dependencies() -> None:
    """Ensure analysis only runs with the required NLP libraries installed."""
    global _CHECKED
    if _CHECKED:
        return

    missing = []

    try:
        import_module("jieba")
        import_module("jieba.analyse")
    except ImportError:
        missing.append("jieba")

    try:
        import_module("snownlp")
    except ImportError:
        missing.append("snownlp")

    try:
        import_module("sklearn.feature_extraction.text")
        import_module("sklearn.metrics.pairwise")
    except ImportError:
        missing.append("scikit-learn")

    if missing:
        raise AnalysisDependencyError(
            "analysis 模块缺少必要依赖："
            + "、".join(missing)
            + "。请先安装 jieba、snownlp、scikit-learn 后再运行分析。"
        )

    _CHECKED = True


def get_jieba():
    check_required_dependencies()
    return import_module("jieba")


def get_jieba_analyse():
    check_required_dependencies()
    return import_module("jieba.analyse")


def get_snownlp_class():
    check_required_dependencies()
    return import_module("snownlp").SnowNLP


def get_sklearn_similarity_tools():
    check_required_dependencies()
    vectorizer_module = import_module("sklearn.feature_extraction.text")
    pairwise_module = import_module("sklearn.metrics.pairwise")
    return vectorizer_module.TfidfVectorizer, pairwise_module.cosine_similarity
