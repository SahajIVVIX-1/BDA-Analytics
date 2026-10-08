"""Server-side JSON Schema validation for the `posts` collection.

The validator guarantees the fields every analytics pipeline depends on
(`post_id`, `text`, `created_at`, `hashtags`, ...) exist with the right BSON
types, while leaving the document flexible elsewhere (the point of a document
store). `validationAction="error"` makes MongoDB reject a malformed document
even if it bypasses the Python ingestion pipeline.
"""

from pymongo.database import Database
from pymongo.errors import CollectionInvalid

from app.database import mongo

POSTS_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["post_id", "text", "clean_text", "created_at", "hashtags", "mentions", "processed", "source"],
        "properties": {
            "post_id": {"bsonType": "string", "minLength": 1},
            "source": {"bsonType": "string"},
            "text": {"bsonType": "string", "minLength": 1},
            "clean_text": {"bsonType": "string"},
            "created_at": {"bsonType": "date"},
            "language": {"bsonType": ["string", "null"]},
            "hashtags": {"bsonType": "array", "items": {"bsonType": "string"}},
            "mentions": {"bsonType": "array", "items": {"bsonType": "string"}},
            "processed": {"bsonType": "bool"},
            "user": {
                "bsonType": "object",
                "properties": {
                    "username": {"bsonType": "string"},
                    "followers": {"bsonType": ["int", "long", "null"], "minimum": 0},
                },
            },
            "location": {"bsonType": ["object", "null"]},
            "engagement": {
                "bsonType": ["object", "null"],
                "properties": {
                    "likes": {"bsonType": ["int", "long"], "minimum": 0},
                    "comments": {"bsonType": ["int", "long"], "minimum": 0},
                    "shares": {"bsonType": ["int", "long"], "minimum": 0},
                    "total": {"bsonType": ["int", "long"], "minimum": 0},
                    "synthetic": {"bsonType": "bool"},
                },
            },
            "sentiment": {
                "bsonType": ["object", "null"],
                "properties": {
                    "label": {"enum": ["positive", "neutral", "negative", None]},
                    "score": {"bsonType": ["double", "null"]},
                },
            },
        },
    }
}


def ensure_posts_collection(db: Database | None = None) -> None:
    db = db if db is not None else mongo.get_db()
    try:
        db.create_collection(mongo.POSTS, validator=POSTS_VALIDATOR, validationLevel="strict",
                             validationAction="error")
    except CollectionInvalid:
        db.command("collMod", mongo.POSTS, validator=POSTS_VALIDATOR, validationLevel="strict",
                   validationAction="error")


def init_database(db: Database | None = None, include_text_index: bool = True) -> list[str]:
    from app.database.indexes import ensure_indexes

    db = db if db is not None else mongo.get_db()
    ensure_posts_collection(db)
    return ensure_indexes(db, include_text=include_text_index)
