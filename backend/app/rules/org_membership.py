"""Pure guard rules for organization-membership mutations.

Kept LLM-free and DB-free so the "you cannot lock yourself out of your own
org" invariants are unit-testable in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.rbac import ADMIN_ROLES, OrgRole


@dataclass(frozen=True)
class MemberView:
    member_id: str
    role: OrgRole
    is_active: bool


def active_admin_count(members: list[MemberView]) -> int:
    return sum(1 for m in members if m.is_active and m.role in ADMIN_ROLES)


def would_remove_last_admin(
    members: list[MemberView],
    *,
    target_member_id: str,
    new_role: OrgRole | None,
    new_is_active: bool | None,
) -> bool:
    """True if applying the change would leave the org with zero active admins."""
    updated: list[MemberView] = []
    for m in members:
        if m.member_id == target_member_id:
            updated.append(
                MemberView(
                    member_id=m.member_id,
                    role=new_role if new_role is not None else m.role,
                    is_active=new_is_active if new_is_active is not None else m.is_active,
                )
            )
        else:
            updated.append(m)
    return active_admin_count(updated) == 0
