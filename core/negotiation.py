from rest_framework.negotiation import DefaultContentNegotiation
from rest_framework import exceptions

class IgnoreUnsupportedFormatContentNegotiation(DefaultContentNegotiation):
    """Allow custom export formats without raising NotAcceptable.

    DRF normally uses the format query parameter as part of content
    negotiation and can return 406/404 when a format like `csv` is not
    available from the registered renderers. For custom export endpoints
    that handle `format=csv|xlsx|pdf` manually, we ignore unsupported
    URL format overrides and fall back to the default renderer.
    """
    def select_renderer(self, request, renderers, format_suffix=None):
        try:
            return super().select_renderer(request, renderers, format_suffix)
        except exceptions.NotAcceptable:
            return renderers[0], renderers[0].media_type
