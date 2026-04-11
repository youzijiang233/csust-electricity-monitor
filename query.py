"""电费 API 查询"""

import time
import logging

import requests

from auth import TokenManager

logger = logging.getLogger(__name__)

CHARGE_AUTH = "Basic Y2hhcmdlOmNoYXJnZV9zZWNyZXQ="


class QueryError(Exception):
    pass


def fetch_electricity(config: dict, token_manager: TokenManager,
                      room_id: str = None, room_name: str = None,
                      loudong_id: str = None, building_name: str = None) -> dict:
    """查询单个房间电费，room_id/room_name/loudong_id 不传则使用 config 中的值"""
    api = config["api"]
    token = token_manager.token

    rid = room_id or api.get("room_id", "")
    lid = loudong_id or api.get("loudong_id", "")
    resp = requests.post(
        f"{api['base_url']}/charge/feeitem/getThirdData",
        data={
            "xiaoqu_id": api["xiaoqu_id"],
            "loudong_id": lid,
            "room_id": rid,
            "type": api["type"],
            "level": api["level"],
            "feeitemid": api["feeitemid"],
        },
        headers={
            "Authorization": CHARGE_AUTH,
            "synjones-auth": f"bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        timeout=30,
    )
    resp.raise_for_status()
    result = resp.json()

    if result.get("code") != 200:
        raise QueryError(f"查询失败: {result.get('msg', result)}")

    data = result["map"]["data"]
    show = result["map"]["showData"]

    return {
        "remaining_kwh": float(show.get("剩余电量", 0)),
        "total_kwh": float(data.get("allAmp", 0)),
        "used_kwh": float(data.get("usedAmp", 0)),
        "room_id": data.get("room_id", rid),
        "room_name": room_name or "",
        "building_id": data.get("loudong_id", ""),
        "building_name": building_name or "",
        "campus_id": data.get("xiaoqu_id", ""),
        "raw": result,
    }


def fetch_all_rooms(config: dict, token_manager: TokenManager,
                    rooms: list[dict], interval: float = 2.0, label: str = "查询"):
    """
    顺序查询所有房间，每次间隔 interval 秒。
    rooms: [{"name": "A101", "value": "49000"}, ...]
    每查询一条 yield 结果字典，失败时 yield None（含 room_id/room_name）。
    label: 日志前缀，默认"查询"，补查时传"补查"
    """
    for i, room in enumerate(rooms):
        if i > 0:
            time.sleep(interval)
        room_id = room["value"]
        room_name = room["name"]
        try:
            data = fetch_electricity(config, token_manager,
                                     room_id=room_id, room_name=room_name,
                                     loudong_id=room.get("loudong_id"),
                                     building_name=room.get("building_name"))
            logger.info("%s成功 [%s/%s] %s: %.2f kWh",
                        label, i + 1, len(rooms), room_name, data["remaining_kwh"])
            yield data
        except Exception as e:
            logger.error("%s失败 [%s/%s] %s: %s", label, i + 1, len(rooms), room_name, e)
            yield None


if __name__ == "__main__":
    import json
    import yaml
    logging.basicConfig(level=logging.INFO)
    with open("config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    with open(cfg["rooms"]["json_path"], "r", encoding="utf-8") as f:
        rooms_data = json.load(f)
    rooms = rooms_data["map"]["data"]
    tm = TokenManager(cfg)
    for result in fetch_all_rooms(cfg, tm, rooms):
        if result:
            print(f"{result['room_name']}: {result['remaining_kwh']} kWh")
