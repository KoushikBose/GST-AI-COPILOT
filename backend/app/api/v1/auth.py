"""Authentication endpoints: register, login, refresh, current-user."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db_session
from app.core.rate_limit import limiter
from app.models.rbac import OrganizationMember
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    OrganizationMembershipOut,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from app.schemas.organization import UpdateProfileRequest
from app.security.dependencies import AuthenticatedUser, get_authenticated_user
from app.services.auth_service import AuthService
from app.services.organization_service import OrganizationService

router = APIRouter()


@router.post("/register", response_model=TokenResponse, status_code=201)
@limiter.limit("10/minute")
async def register(
    request: Request,
    body: RegisterRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    service = AuthService(session)
    user, _organization, membership = await service.register(
        email=body.email,
        password=body.password,
        full_name=body.full_name,
        organization_name=body.organization_name,
    )
    access, refresh = service.issue_tokens(user, membership)
    await session.commit()
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("20/minute")
async def login(
    request: Request,
    body: LoginRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    service = AuthService(session)
    user, membership = await service.authenticate(
        email=body.email, password=body.password, organization_id=body.organization_id
    )
    access, refresh = service.issue_tokens(user, membership)
    await session.commit()
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("30/minute")
async def refresh(
    request: Request,
    body: RefreshRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    service = AuthService(session)
    access, new_refresh = await service.refresh_access_token(body.refresh_token)
    await session.commit()
    return TokenResponse(access_token=access, refresh_token=new_refresh)


@router.get("/me", response_model=UserOut)
async def me(
    auth_user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db_session),
) -> UserOut:
    stmt = (
        select(User)
        .where(User.id == auth_user.user_id)
        .options(selectinload(User.memberships).selectinload(OrganizationMember.organization))
    )
    result = await session.execute(stmt)
    user = result.scalar_one()

    memberships_out = [
        OrganizationMembershipOut(
            organization_id=m.organization_id,
            organization_name=m.organization.name,
            role=m.role,
        )
        for m in user.memberships
        if m.is_active
    ]
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        is_email_verified=user.is_email_verified,
        memberships=memberships_out,
    )


@router.patch("/me", response_model=UserOut)
async def update_me(
    body: UpdateProfileRequest,
    auth_user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db_session),
) -> UserOut:
    service = OrganizationService(session)
    await service.update_profile(
        user_id=auth_user.user_id,
        full_name=body.full_name,
        current_password=body.current_password,
        new_password=body.new_password,
    )
    await session.commit()

    stmt = (
        select(User)
        .where(User.id == auth_user.user_id)
        .options(selectinload(User.memberships).selectinload(OrganizationMember.organization))
    )
    result = await session.execute(stmt)
    user = result.scalar_one()
    memberships_out = [
        OrganizationMembershipOut(
            organization_id=m.organization_id,
            organization_name=m.organization.name,
            role=m.role,
        )
        for m in user.memberships
        if m.is_active
    ]
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        is_email_verified=user.is_email_verified,
        memberships=memberships_out,
    )
