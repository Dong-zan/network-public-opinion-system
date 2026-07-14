from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class SourceDescriptor:
    source: str
    url: str


class SourceClusterer:
    def cluster_indices(self, items: list[SourceDescriptor]) -> list[int]:
        parents = list(range(len(items)))

        def find(index: int) -> int:
            while parents[index] != index:
                parents[index] = parents[parents[index]]
                index = parents[index]
            return index

        def union(left: int, right: int) -> None:
            left_root = find(left)
            right_root = find(right)
            if left_root != right_root:
                parents[right_root] = left_root

        identities = [self.identity(item) for item in items]
        for left in range(len(items)):
            for right in range(left + 1, len(items)):
                same_source = (
                    identities[left][0]
                    and identities[left][0] == identities[right][0]
                )
                same_host = (
                    identities[left][1]
                    and identities[left][1] == identities[right][1]
                )
                if same_source or same_host:
                    union(left, right)
        return [find(index) for index in range(len(items))]

    @staticmethod
    def identity(item: SourceDescriptor) -> tuple[str, str]:
        return (
            item.source.strip().lower(),
            (urlparse(item.url).hostname or "").lower(),
        )
