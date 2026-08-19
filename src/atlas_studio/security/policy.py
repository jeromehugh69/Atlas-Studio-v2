"""Policy Engine - Enforces access control and security policies."""
from __future__ import annotations

from typing import Any

from fastapi import Request


class PolicyEngine:
    """Enforce security policies on all requests.
    
    Policies define:
    - Which paths require specific permissions
    - Which methods are allowed for each path
    - Role-based access control
    - Rate limiting per endpoint
    """

    # Paths that require specific permissions
    PROTECTED_PATHS: dict[str, dict[str, Any]] = {
        "/api/agents": {
            "POST": {"required_role": "admin", "description": "Create agent"},
            "DELETE": {"required_role": "admin", "description": "Delete agent"},
            "PATCH": {"required_role": "developer", "description": "Update agent"},
        },
        "/api/change-sets": {
            "POST": {"required_role": "developer", "description": "Create change set"},
            "DELETE": {"required_role": "admin", "description": "Delete change set"},
            "PATCH": {"required_role": "developer", "description": "Update change set"},
        },
        "/api/lifecycles": {
            "POST": {"required_role": "developer", "description": "Create lifecycle"},
            "PATCH": {"required_role": "developer", "description": "Update lifecycle"},
            "DELETE": {"required_role": "admin", "description": "Delete lifecycle"},
        },
        "/api/plans": {
            "POST": {"required_role": "developer", "description": "Create plan"},
            "DELETE": {"required_role": "admin", "description": "Delete plan"},
        },
        "/api/tasks": {
            "DELETE": {"required_role": "admin", "description": "Delete task"},
        },
        "/api/external-approvals": {
            "POST": {"required_role": "developer", "description": "Approve external action"},
        },
    }

    # Paths that are always public (no auth required)
    PUBLIC_PATHS = [
        "/api/health/live",
        "/api/health/ready",
        "/api/config",
        "/static/",
        "/api/docs",
        "/openapi.json",
    ]

    # Rate limits per endpoint (requests per minute)
    RATE_LIMITS: dict[str, int] = {
        "/api/tasks": 30,
        "/api/agents": 20,
        "/api/lifecycles": 10,
        "/api/change-sets": 10,
        "/api/intake": 5,
    }

    def evaluate(self, request: Request, user: str | None) -> dict[str, Any]:
        """Evaluate if request is allowed based on policy.
        
        Args:
            request: The incoming HTTP request
            user: The authenticated user (if any)
            
        Returns:
            dict with 'allowed', 'policy', and optional 'reason'
        """
        path = str(request.url.path)
        method = request.method

        # Check public paths first
        for public_path in self.PUBLIC_PATHS:
            if path.startswith(public_path):
                return {"allowed": True, "policy": "public"}

        # Check protected paths
        for protected_path, methods in self.PROTECTED_PATHS.items():
            if path.startswith(protected_path) and method in methods:
                rules = methods[method]
                required_role = rules["required_role"]

                # Check if user has required role
                if user and self._has_role(user, required_role):
                    return {
                        "allowed": True,
                        "policy": "protected",
                        "role": required_role,
                    }
                return {
                    "allowed": False,
                    "policy": "protected",
                    "reason": f"Requires {required_role} role",
                }

        # Check rate limits
        rate_limit = self._get_rate_limit(path)
        if rate_limit:
            # Rate limiting is handled by MITM middleware
            pass

        # Default: allow for local user in community mode
        return {"allowed": True, "policy": "default"}

    def _has_role(self, user: str, role: str) -> bool:
        """Check if user has required role.
        
        In local-first community mode, all local users have all roles.
        """
        # Local users have all roles in community mode
        if user in ("local-user", "worker", "api-user"):
            return True
        return False

    def _get_rate_limit(self, path: str) -> int | None:
        """Get rate limit for a path."""
        for pattern, limit in self.RATE_LIMITS.items():
            if path.startswith(pattern):
                return limit
        return None

    def add_policy(self, path: str, method: str, required_role: str) -> None:
        """Add a new policy rule."""
        if path not in self.PROTECTED_PATHS:
            self.PROTECTED_PATHS[path] = {}
        self.PROTECTED_PATHS[path][method] = {
            "required_role": required_role,
        }

    def remove_policy(self, path: str, method: str | None = None) -> None:
        """Remove a policy rule."""
        if path in self.PROTECTED_PATHS:
            if method:
                self.PROTECTED_PATHS[path].pop(method, None)
                if not self.PROTECTED_PATHS[path]:
                    del self.PROTECTED_PATHS[path]
            else:
                del self.PROTECTED_PATHS[path]

    def get_policies(self) -> dict[str, Any]:
        """Get all current policies."""
        return {
            "protected_paths": self.PROTECTED_PATHS,
            "public_paths": self.PUBLIC_PATHS,
            "rate_limits": self.RATE_LIMITS,
        }
