"""NLP intelligent analysis module for public-opinion news items."""

from .analysis_pipeline import analyze_news, analyze_news_batch
from .dependencies import AnalysisDependencyError, check_required_dependencies
from .preprocess import preprocess_news, preprocess_news_batch
from .summary import generate_summary

__all__ = [
    "AnalysisDependencyError",
    "analyze_news",
    "analyze_news_batch",
    "check_required_dependencies",
    "preprocess_news",
    "preprocess_news_batch",
    "generate_summary",
]
