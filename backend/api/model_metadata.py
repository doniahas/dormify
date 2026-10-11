"""
Generic Django model-metadata helpers that have no single domain owner.

The api.views compatibility facade (api/views/__init__.py) imports
_get_model_field_names from here, so references through the api.views
namespace keep resolving to this same function.
"""


def _get_model_field_names(model_cls):
    return {f.name for f in model_cls._meta.fields}
