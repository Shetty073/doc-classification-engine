import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Enterprise-grade security header injection middleware.
    Protects banking API endpoints against MIME-sniffing, clickjacking,
    cross-site injection, and forces TLS compliance.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.perf_counter()
        response: Response = await call_next(request)
        process_time = time.perf_counter() - start_time

        # Security Headers
        headers = {
            # Enforce HTTPS on clients
            "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
            # Prevent MIME-type sniffing
            "X-Content-Type-Options": "nosniff",
            # Prevent embedding inside iframes (clickjacking protection)
            "X-Frame-Options": "DENY",
            # Enable browser XSS filtering
            "X-XSS-Protection": "1; mode=block",
            # Content Security Policy restricted to trusted origins
            "Content-Security-Policy": (
                "default-src 'none'; "
                "frame-ancestors 'none'; "
                "base-uri 'none'; "
                "form-action 'self';"
            ),
            # Referrer privacy policy
            "Referrer-Policy": "strict-origin-when-cross-origin",
            # Restrict browser device feature access
            "Permissions-Policy": (
                "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
                "magnetometer=(), microphone=(), payment=(), usb=()"
            ),
            # Observability
            "X-Process-Time": f"{process_time:.4f}s",
        }

        for header_name, header_value in headers.items():
            response.headers[header_name] = header_value

        return response
