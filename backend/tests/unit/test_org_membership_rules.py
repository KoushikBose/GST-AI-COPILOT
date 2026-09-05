"""Unit tests for organization-membership guard rules (LLM/DB-free)."""

from __future__ import annotations

from app.models.rbac import OrgRole
from app.rules.org_membership import MemberView, active_admin_count, would_remove_last_admin


def _members():
    return [
        MemberView("m1", OrgRole.ORG_ADMIN, True),
        MemberView("m2", OrgRole.ACCOUNTANT, True),
        MemberView("m3", OrgRole.VIEWER, False),
    ]


def test_active_admin_count_ignores_inactive_and_non_admin():
    members = _members() + [MemberView("m4", OrgRole.ORG_ADMIN, False)]
    assert active_admin_count(members) == 1


def test_demoting_the_only_admin_is_blocked():
    assert would_remove_last_admin(
        _members(), target_member_id="m1", new_role=OrgRole.VIEWER, new_is_active=None
    )


def test_deactivating_the_only_admin_is_blocked():
    assert would_remove_last_admin(
        _members(), target_member_id="m1", new_role=None, new_is_active=False
    )


def test_demoting_one_of_two_admins_is_allowed():
    members = _members() + [MemberView("m5", OrgRole.SUPER_ADMIN, True)]
    assert not would_remove_last_admin(
        members, target_member_id="m1", new_role=OrgRole.VIEWER, new_is_active=None
    )


def test_promoting_a_member_to_admin_is_always_allowed():
    assert not would_remove_last_admin(
        _members(), target_member_id="m2", new_role=OrgRole.ORG_ADMIN, new_is_active=None
    )
