from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class GPGStatus:
    tag: str
    args: List[str] = field(default_factory=list)


@dataclass
class GPGResult:
    ok: bool
    stdout: str
    stderr: str
    returncode: int
    statuses: List[GPGStatus] = field(default_factory=list)

    def status_lines(self) -> List[str]:
        lines: List[str] = []
        for item in self.statuses:
            if item.args:
                lines.append(f"{item.tag} {' '.join(item.args)}")
            else:
                lines.append(item.tag)
        return lines


@dataclass
class GPGKey:
    key_type: str
    key_id: str
    fingerprint: str
    user_ids: List[str]
    trust: str
    capabilities: str
    expired: bool
    revoked: bool
    disabled: bool

    @property
    def primary_uid(self) -> str:
        return self.user_ids[0] if self.user_ids else "(no uid)"
