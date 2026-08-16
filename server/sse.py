"""SSE 事件构造器。

格式（W3C SSE）：
    event: <name>\n
    data: <json>\n\n
"""

import json
from typing import Any, Dict


def sse_event(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
