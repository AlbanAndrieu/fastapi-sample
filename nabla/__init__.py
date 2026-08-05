#!/usr/bin/env python
"""
This module allow to do things.
"""

import uuid

from nabla.version import RELEASE_VERSION

# from dd.dd_api_exporter import counts_by_product_id, get_products

name = "nabla"

signing_uuid = uuid.UUID("dd34b62f-9ed5-597e-85a2-c15d48ed6832")
__version__ = RELEASE_VERSION

# __version__ = 'v1.1.0'

__all__ = ("__version__", "signing_uuid")
