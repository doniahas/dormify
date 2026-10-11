"""
Shared DRF pagination for the api views.

The api.views compatibility facade (api/views/__init__.py) imports
StandardResultsPagination from here, so references through the api.views
namespace keep resolving to this same class.
"""

from rest_framework.pagination import PageNumberPagination


class StandardResultsPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 100
