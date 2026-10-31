"""
Database layer for MongoDB operations.
Provides async Motor client and repository functions.
"""

from ai.db.client import (
    MongoClient,
    get_db,
    test_connection
)

__all__ = [
    "MongoClient",
    "get_db",
    "test_connection"
]
