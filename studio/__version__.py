"""
Single source of version truth for the entire product.

Everything that states a version reads it from here: the FastAPI application,
the packaging metadata, the Chrome extension manifest, and the release tag.
A mismatch between surfaces should be impossible rather than merely discouraged.

Strict Invariants:
- Zero em-dashes.
- Semantic versioning where MAJOR is reserved for a database schema break that
  cannot be migrated forward. See docs/PACKAGING_AND_MAINTENANCE_MASTER_PLAN.md.
"""

__version__ = "2.5.1"
