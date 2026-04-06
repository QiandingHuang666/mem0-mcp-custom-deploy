"""Legacy in-memory OAuth helper retained for compatibility.

Current first-version auth direction is `device token + TLS`, implemented in
`device_tokens.py`. This module is now legacy-only and is no longer the primary
server authentication path.
"""

from __future__ import annotations

import logging
import os
import secrets
import time
from typing import Any, Dict, Optional

from pydantic import AnyUrl

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

logger = logging.getLogger("mem0_mcp_server.auth")

# Default access token lifetime: 24 hours
_ACCESS_TOKEN_TTL = 24 * 60 * 60
# Authorization code lifetime: 10 minutes
_AUTH_CODE_TTL = 10 * 60


class InMemoryOAuthProvider:
    """In-memory OAuth 2.1 Authorization Server provider.

    Implements the ``OAuthAuthorizationServerProvider`` protocol expected by
    ``mcp.server.auth`` middleware.
    """

    def __init__(self) -> None:
        self._clients: Dict[str, OAuthClientInformationFull] = {}
        self._auth_codes: Dict[str, AuthorizationCode] = {}
        self._access_tokens: Dict[str, AccessToken] = {}
        self._refresh_tokens: Dict[str, RefreshToken] = {}

        # Pre-configure a client from environment variables
        client_id = os.getenv("OAUTH_CLIENT_ID", "mem0-mcp-client")
        client_secret = os.getenv("OAUTH_CLIENT_SECRET", "changeme")

        preconf = OAuthClientInformationFull(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uris=[AnyUrl("http://localhost:3000/callback")],
            grant_types=["authorization_code", "refresh_token"],
            token_endpoint_auth_method="client_secret_post",
            scope="memory:read memory:write",
        )
        self._clients[client_id] = preconf
        logger.info("Pre-configured OAuth client: %s", client_id)

    # ------------------------------------------------------------------
    # Client management
    # ------------------------------------------------------------------

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self._clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        self._clients[client_info.client_id] = client_info
        logger.info("Registered new OAuth client: %s", client_info.client_id)

    # ------------------------------------------------------------------
    # Authorization flow
    # ------------------------------------------------------------------

    async def authorize(
        self,
        client: OAuthClientInformationFull,
        params: AuthorizationParams,
    ) -> str:
        """Generate an authorization code and redirect back to the client.

        In a production system this would involve user consent UI; here we
        auto-approve and redirect with the code embedded.
        """
        code_str = secrets.token_urlsafe(48)
        now = time.time()

        auth_code = AuthorizationCode(
            code=code_str,
            scopes=params.scopes or ["memory:read", "memory:write"],
            expires_at=now + _AUTH_CODE_TTL,
            client_id=client.client_id,
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource,
        )
        self._auth_codes[code_str] = auth_code

        from mcp.server.auth.provider import construct_redirect_uri

        redirect_url = construct_redirect_uri(
            str(params.redirect_uri),
            code=code_str,
            state=params.state,
        )
        logger.debug("Issued authorization code for client %s", client.client_id)
        return redirect_url

    async def load_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: str,
    ) -> AuthorizationCode | None:
        code = self._auth_codes.get(authorization_code)
        if code is None or code.client_id != client.client_id:
            return None
        return code

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: AuthorizationCode,
    ) -> OAuthToken:
        """Swap an authorization code for access + refresh tokens."""
        # Invalidate the code
        self._auth_codes.pop(authorization_code.code, None)

        now = time.time()
        access_str = secrets.token_urlsafe(48)
        refresh_str = secrets.token_urlsafe(48)

        access_token = AccessToken(
            token=access_str,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            expires_at=int(now + _ACCESS_TOKEN_TTL),
            resource=authorization_code.resource,
        )
        refresh_token = RefreshToken(
            token=refresh_str,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
        )

        self._access_tokens[access_str] = access_token
        self._refresh_tokens[refresh_str] = refresh_token

        logger.debug("Exchanged auth code for tokens (client=%s)", client.client_id)
        return OAuthToken(
            access_token=access_str,
            token_type="Bearer",
            expires_in=_ACCESS_TOKEN_TTL,
            scope=" ".join(authorization_code.scopes),
            refresh_token=refresh_str,
        )

    # ------------------------------------------------------------------
    # Refresh token flow
    # ------------------------------------------------------------------

    async def load_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: str,
    ) -> RefreshToken | None:
        rt = self._refresh_tokens.get(refresh_token)
        if rt is None or rt.client_id != client.client_id:
            return None
        return rt

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        # Rotate: invalidate old refresh token
        self._refresh_tokens.pop(refresh_token.token, None)

        now = time.time()
        new_access_str = secrets.token_urlsafe(48)
        new_refresh_str = secrets.token_urlsafe(48)
        effective_scopes = scopes or refresh_token.scopes

        new_access = AccessToken(
            token=new_access_str,
            client_id=client.client_id,
            scopes=effective_scopes,
            expires_at=int(now + _ACCESS_TOKEN_TTL),
        )
        new_refresh = RefreshToken(
            token=new_refresh_str,
            client_id=client.client_id,
            scopes=effective_scopes,
        )

        self._access_tokens[new_access_str] = new_access
        self._refresh_tokens[new_refresh_str] = new_refresh

        logger.debug("Rotated refresh token for client %s", client.client_id)
        return OAuthToken(
            access_token=new_access_str,
            token_type="Bearer",
            expires_in=_ACCESS_TOKEN_TTL,
            scope=" ".join(effective_scopes),
            refresh_token=new_refresh_str,
        )

    # ------------------------------------------------------------------
    # Access token verification
    # ------------------------------------------------------------------

    async def load_access_token(self, token: str) -> AccessToken | None:
        at = self._access_tokens.get(token)
        if at is None:
            return None
        if at.expires_at is not None and time.time() > at.expires_at:
            self._access_tokens.pop(token, None)
            return None
        return at

    # ------------------------------------------------------------------
    # Revocation
    # ------------------------------------------------------------------

    async def revoke_token(
        self,
        token: AccessToken | RefreshToken,
    ) -> None:
        if isinstance(token, AccessToken):
            self._access_tokens.pop(token.token, None)
        else:
            self._refresh_tokens.pop(token.token, None)
        logger.debug("Revoked token")
