"""Catalogue loading and normalized record types."""

from .loader import load_contractors
from .models import Contractor

__all__ = ["Contractor", "load_contractors"]
