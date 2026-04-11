"""定时查询调度"""

import json
import logging
import re
import time
from pathlib import Path
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from auth import TokenManager
from db import Database
from query import fetch_all_rooms

logger = logging.getLogger(__name__)


def load_all_buildings(buildings_dir: str) -> list[dict]:
    """
    扫描 buildings/ 目录，读取所有 json 文件。
    文件名格式: 楼栋名_楼栋id.json，例如 至诚轩5栋A区_557.json
    返回房间列表，每项含 name, value(room_id), loudong_id, building_name
    """
    rooms = []
    for path in sorted(Path(buildings_dir).glob("*.json")):
        m = re.match(r"^(.+)_(\d+)\.json$", path.name)
        if not m:
            logger.warning("跳过不符合命名规范的文件: %s", path.name)
            continue
        building_name, loudong_id = m.group(1), m.group(2)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for room in data["map"]["data"]:
                rooms.append({
                    "name": room["name"],
                    "value": room["value"],
                    "loudong_id": loudong_id,
                    "building_name": building_name,
                })
        except Exception as e:
            logger.error("读取楼栋文件失败 %s: %s", path.name, e)
    return rooms


class ElectricityScheduler:
    def __init__(self, config: dict, db: Database, token_manager: TokenManager):
        self.config = config
        self.db = db
        self.token_manager = token_manager
        self.scheduler = BackgroundScheduler()
        self.last_error = None
        self._rooms = self._load_rooms()

    def _load_rooms(self) -> list[dict]:
        buildings_dir = self.config["rooms"]["buildings_dir"]
        rooms = load_all_buildings(buildings_dir)
        logger.info("已加载 %d 个楼栋文件，共 %d 个房间",
                    len(set(r["loudong_id"] for r in rooms)), len(rooms))
        return rooms

    def start(self):
        hours = self.config["schedule"]["query_hours"]
        hours_str = ",".join(str(h) for h in hours)
        self.scheduler.add_job(
            self._query_and_store,
            trigger=CronTrigger(hour=hours_str, minute=0),
            id="electricity_query",
            replace_existing=True,
        )
        self.scheduler.start()
        logger.info("调度器已启动，每天 %s 点查询，共 %d 个房间", hours_str, len(self._rooms))

        if self.config["schedule"].get("start_immediately", False):
            self._query_and_store()

    def stop(self):
        self.scheduler.shutdown(wait=False)

    def _query_and_store(self):
        # 先确保 token 有效，避免批量查询中途反复登录
        try:
            _ = self.token_manager.token
        except Exception as e:
            self.last_error = f"登录失败，跳过本轮查询: {e}"
            logger.error(self.last_error)
            return

        logger.info("开始批量查询，共 %d 个房间...", len(self._rooms))
        interval = self.config["rooms"].get("query_interval_ms", 2000) / 1000.0
        success = 0
        failed_rooms = []
        for i, data in enumerate(fetch_all_rooms(self.config, self.token_manager, self._rooms, interval=interval)):
            if data:
                try:
                    self.db.insert_reading(data)
                    success += 1
                except Exception as e:
                    logger.error("写入数据库失败 %s: %s", data.get("room_name"), e)
                    failed_rooms.append(self._rooms[i])
            else:
                failed_rooms.append(self._rooms[i])

        # 补查失败的房间
        if failed_rooms:
            retry_wait = self.config["rooms"].get("retry_wait_ms", 15000) / 1000.0
            retry_interval = self.config["rooms"].get("retry_interval_ms", 4000) / 1000.0
            logger.info("本轮失败 %d 个，等待 %.0f 秒后开始补查...", len(failed_rooms), retry_wait)
            time.sleep(retry_wait)
            retry_fail = 0
            for i, data in enumerate(fetch_all_rooms(self.config, self.token_manager, failed_rooms,
                                                     interval=retry_interval, label="补查")):
                if data:
                    try:
                        self.db.insert_reading(data)
                        success += 1
                    except Exception as e:
                        logger.error("写入数据库失败 %s: %s", data.get("room_name"), e)
                        retry_fail += 1
                else:
                    retry_fail += 1
            logger.info("补查完成: 成功 %d，失败 %d", len(failed_rooms) - retry_fail, retry_fail)
            self.last_error = f"本轮失败 {retry_fail} 个（已补查）" if retry_fail else None
        else:
            self.last_error = None

        total_fail = retry_fail if failed_rooms else 0
        logger.info("批量查询完成: 成功 %d，失败 %d", success, total_fail)

    def get_next_run(self) -> str:
        job = self.scheduler.get_job("electricity_query")
        if job and job.next_run_time:
            return job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")
        return ""
