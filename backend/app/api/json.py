"""JSON response class that understands BSON / NumPy types."""

import json
from datetime import date, datetime
from decimal import Decimal

import numpy as np
from bson import ObjectId
from fastapi.responses import JSONResponse


def _default(o):
    if isinstance(o, datetime):
        return o.isoformat().replace("+00:00", "Z")
    if isinstance(o, date):
        return o.isoformat()
    if isinstance(o, ObjectId):
        return str(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, Decimal):
        return float(o)
    if isinstance(o, set):
        return sorted(o)
    raise TypeError(f"{type(o).__name__} is not JSON serialisable")


class MongoJSONResponse(JSONResponse):
    def render(self, content) -> bytes:
        return json.dumps(content, default=_default, ensure_ascii=False, separators=(",", ":"),
                          allow_nan=False).encode("utf-8")
