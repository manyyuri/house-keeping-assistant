"""口味偏好：忌口食材 + 爱好的菜系。

规则引擎直接读本地 JSON（server/data/preferences.json，gitignored，用户私有）。
缺文件 / 解析失败时回退到代码默认（中性：无忌口、不偏菜系）。
结构判定不经 LLM，与 rules / meal_rules 同哲学（防幻觉、离线可用）。
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger("danshari.preferences")

DATA_DIR = Path(__file__).resolve().parent / "data"
PREFS_PATH = DATA_DIR / "preferences.json"

DEFAULTS: Dict[str, Any] = {
    "disliked_ingredients": [],  # 忌口食材，如 ["荷兰豆"]
    "preferred_cuisines": [],  # 偏好的菜系，与菜谱 cuisine 字段对齐，如 ["川菜", "粤菜"]
}


def load() -> Dict[str, Any]:
    try:
        data = json.loads(PREFS_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return dict(DEFAULTS)
    except Exception:  # noqa: BLE001 — 偏好文件坏了不至于让三餐崩掉
        logger.warning("偏好文件解析失败，回退默认（%s）", PREFS_PATH)
        return dict(DEFAULTS)
    if not isinstance(data, dict):
        return dict(DEFAULTS)
    return {**DEFAULTS, **data}


def save(prefs: Dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PREFS_PATH.write_text(
        json.dumps(prefs, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------- 纯函数判定（引擎与单测共用） ----------


def recipe_text(r: Dict[str, Any]) -> str:
    """把一道菜的菜名 + 各餐位食材 + 用料名拼成检索文本（忌口匹配用）。"""
    parts = [str(r.get("name") or "")]
    for s in r.get("slots") or []:
        parts.append(str(s.get("food") or ""))
    for i in r.get("ingredients") or []:
        parts.append(str(i.get("name") or ""))
    return "".join(parts)


def allowed(recipe: Dict[str, Any], prefs: Dict[str, Any]) -> bool:
    """不含任何忌口食材 → 可吃。"""
    disliked = [d for d in (prefs.get("disliked_ingredients") or []) if d]
    if not disliked:
        return True
    txt = recipe_text(recipe)
    return not any(d in txt for d in disliked)


def favored(recipe: Dict[str, Any], prefs: Dict[str, Any]) -> bool:
    """菜系属于偏好列表 → 优先推。"""
    fav = [c for c in (prefs.get("preferred_cuisines") or []) if c]
    if not fav:
        return False
    return (recipe.get("cuisine") or "") in fav


def split_pool(
    recipes: List[Dict[str, Any]], prefs: Dict[str, Any]
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """忌口剔除后返回 (可吃池, 其中偏好菜系子集)。调用方负责在空池时兜底。"""
    eat = [r for r in recipes if allowed(r, prefs)]
    pref = [r for r in eat if favored(r, prefs)]
    return eat, pref
