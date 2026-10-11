"""
Error-body builders for the hand-written views.

The API has three hand-written error families (besides DRF's own
``{'detail': ...}`` bodies raised by permissions, throttling, 404s and
serializer validation):

``error_response``   -> ``{'error': <he>[, 'errorEn': <en>][, ...extra]}``
``failure_response`` -> ``{'success': False, 'error': <he>[, 'errorEn': <en>][, ...extra]}``

Key order is preserved as the views always wrote it, so the rendered JSON
is byte-identical to the pre-R6 bodies. ``extra`` carries the per-endpoint
keys some bodies add (``status``, ``error_code``, ``run_id``, ``violations``
...) in the order they are passed.
"""

from rest_framework.response import Response


def error_body(error, *, error_en=None, **extra):
    """``{'error': error[, 'errorEn': error_en], **extra}``."""
    body = {'error': error}
    if error_en is not None:
        body['errorEn'] = error_en
    body.update(extra)
    return body


def failure_body(error, *, error_en=None, **extra):
    """``{'success': False, 'error': error[, 'errorEn': error_en], **extra}``."""
    body = {'success': False, 'error': error}
    if error_en is not None:
        body['errorEn'] = error_en
    body.update(extra)
    return body


def error_response(status_code, error, *, error_en=None, **extra):
    """A DRF Response carrying ``error_body(...)`` with ``status_code``."""
    return Response(error_body(error, error_en=error_en, **extra), status=status_code)


def failure_response(status_code, error, *, error_en=None, **extra):
    """A DRF Response carrying ``failure_body(...)`` with ``status_code``."""
    return Response(failure_body(error, error_en=error_en, **extra), status=status_code)
