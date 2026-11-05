"""Country-specific data source connectors for DataMine Pro.

Connectors must only use public sources whose access and reuse conditions
have been reviewed. A public webpage is not automatically licensed for reuse.
"""
from .registry import get_country_capabilities, list_country_capabilities

__all__ = ["get_country_capabilities", "list_country_capabilities"]
