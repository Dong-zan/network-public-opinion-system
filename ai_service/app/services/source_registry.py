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
