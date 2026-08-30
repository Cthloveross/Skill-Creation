"""Small HTTP transport helpers shared by security-sensitive local clients."""

from __future__ import annotations

import urllib.request
from typing import Any


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        del req, fp, code, msg, headers, newurl
        return None


def no_redirect_urlopen(request: urllib.request.Request, *, timeout: float) -> Any:
    """Open one request while treating every redirect as an HTTP error."""

    return urllib.request.build_opener(_RejectRedirects()).open(request, timeout=timeout)


__all__ = ["no_redirect_urlopen"]
