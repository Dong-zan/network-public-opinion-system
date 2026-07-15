from dataclasses import dataclass


@dataclass(frozen=True)
class SourceProfile:
    canonical_name: str
    aliases: tuple[str, ...] = ()
    verified_domains: tuple[str, ...] = ()
    source_category: str | None = None
    ownership_type: str | None = None
    registry_version: str = "source-registry-v1"

    def matches_name(self, value: str) -> bool:
        normalized = value.strip().casefold()
        return normalized in {
            self.canonical_name.strip().casefold(),
            *(alias.strip().casefold() for alias in self.aliases),
        }


class SourceRegistry:
    """Read-only local registry; this component never performs a network lookup."""

    registry_version = "source-registry-v1"

    @property
    def is_configured(self) -> bool:
        return True

    def find(self, source_name: str) -> SourceProfile | None:
        raise NotImplementedError


class StaticSourceRegistry(SourceRegistry):
    def __init__(self, profiles: tuple[SourceProfile, ...] = ()) -> None:
        self._profiles = tuple(profiles)

    @property
    def is_configured(self) -> bool:
        return bool(self._profiles)

    def find(self, source_name: str) -> SourceProfile | None:
        normalized = source_name.strip()
        if not normalized:
            return None
        return next((profile for profile in self._profiles if profile.matches_name(normalized)), None)


InMemorySourceRegistry = StaticSourceRegistry


def project_source_registry() -> StaticSourceRegistry:
    """Return the local identities for sources collected by this project.

    The registry is deliberately small and static.  A name match alone is not
    enough: ``SourceTraceabilityEvaluator`` also requires the article hostname
    to match one of the configured domains before treating the identity as
    verified.
    """

    return StaticSourceRegistry(
        (
            SourceProfile(
                canonical_name="人民网",
                aliases=("people",),
                verified_domains=("people.com.cn",),
                source_category="官方新闻媒体",
                ownership_type="中央媒体",
                registry_version="project-crawler-sources-v1",
            ),
            SourceProfile(
                canonical_name="新华网",
                aliases=("xinhua",),
                verified_domains=("news.cn",),
                source_category="官方新闻媒体",
                ownership_type="中央媒体",
                registry_version="project-crawler-sources-v1",
            ),
            SourceProfile(
                canonical_name="中新网",
                aliases=("中国新闻网", "chinanews"),
                verified_domains=("chinanews.com.cn",),
                source_category="官方新闻媒体",
                ownership_type="中央媒体",
                registry_version="project-crawler-sources-v1",
            ),
            SourceProfile(
                canonical_name="新浪新闻",
                aliases=("sina",),
                verified_domains=("sina.com.cn",),
                source_category="新闻门户",
                ownership_type="商业媒体平台",
                registry_version="project-crawler-sources-v1",
            ),
        )
    )
