"""
Clerk JWT Authentication for FastAPI

This module provides JWT token verification for Clerk authentication.
It fetches the JWKS (JSON Web Key Set) from Clerk and verifies tokens.
"""

import jwt  # pyright: ignore[reportMissingImports]
import httpx  # pyright: ignore[reportMissingImports]
from typing import Optional
from functools import lru_cache
from pydantic import BaseModel  # pyright: ignore[reportMissingImports]
from fastapi import HTTPException, status, Depends  # pyright: ignore[reportMissingImports]
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.config import settings


class ClerkUser(BaseModel):
    """Represents a verified Clerk user from JWT claims"""
    user_id: str
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None


# Security scheme for Bearer token
security = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def get_clerk_jwks_url() -> str:
    """Get the JWKS URL from Clerk issuer"""
    issuer = settings.CLERK_ISSUER_URL.rstrip("/")
    return f"{issuer}/.well-known/jwks.json"


async def fetch_jwks() -> dict:
    """Fetch the JSON Web Key Set from Clerk"""
    jwks_url = get_clerk_jwks_url()
    async with httpx.AsyncClient() as client:
        response = await client.get(jwks_url)
        response.raise_for_status()
        return response.json()


def get_public_key(jwks: dict, kid: str) -> Optional[str]:
    """Get the public key from JWKS by key ID"""
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return jwt.algorithms.RSAAlgorithm.from_jwk(key)
    return None


async def verify_clerk_token(token: str) -> ClerkUser:
    """
    Verify a Clerk JWT token and return the user claims.

    Args:
        token: The JWT token from the Authorization header

    Returns:
        ClerkUser with verified claims

    Raises:
        HTTPException: If token is invalid or verification fails
    """
    try:
        # Decode header to get key ID
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")

        if not kid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing key ID"
            )

        # Fetch JWKS and get public key
        jwks = await fetch_jwks()
        public_key = get_public_key(jwks, kid)

        if not public_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: key not found"
            )

        # Verify and decode the token
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            options={"verify_aud": False}  # Clerk doesn't always set audience
        )

        # Extract user info from claims
        return ClerkUser(
            user_id=payload.get("sub", ""),
            email=payload.get("email"),
            first_name=payload.get("first_name"),
            last_name=payload.get("last_name"),
        )

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}"
        )
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to verify token: authentication service unavailable"
        )


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> ClerkUser:
    """
    FastAPI dependency to get the current authenticated user.

    Usage:
        @router.get("/protected")
        async def protected_route(user: ClerkUser = Depends(get_current_user)):
            return {"user_id": user.user_id}
    """
    if not settings.CLERK_AUTH_ENABLED:
        # Auth disabled - return a placeholder user for development
        return ClerkUser(user_id="dev-user", email="dev@example.com")

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return await verify_clerk_token(credentials.credentials)


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[ClerkUser]:
    """
    FastAPI dependency for optional authentication.
    Returns None if no token provided, user if valid token.

    Usage:
        @router.get("/optional-auth")
        async def optional_route(user: Optional[ClerkUser] = Depends(get_optional_user)):
            if user:
                return {"authenticated": True, "user_id": user.user_id}
            return {"authenticated": False}
    """
    if not settings.CLERK_AUTH_ENABLED:
        return None

    if not credentials:
        return None

    try:
        return await verify_clerk_token(credentials.credentials)
    except HTTPException:
        return None
