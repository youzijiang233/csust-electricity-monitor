"""SQLite 数据库操作"""

import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path


class Database:
    def __init__(self, db_path: str = "electricity.db"):
        self._db = sqlite3.connect(str(Path(db_path)), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                remaining_kwh REAL NOT NULL,
                total_kwh REAL NOT NULL,
                used_kwh REAL NOT NULL,
                room_id TEXT NOT NULL,
                room_name TEXT NOT NULL DEFAULT '',
                building_id TEXT NOT NULL,
                building_name TEXT NOT NULL DEFAULT '',
                campus_id TEXT NOT NULL,
                raw_json TEXT
            )
        """)
        self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_readings_timestamp
            ON readings(timestamp)
        """)
        self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_readings_room_id
            ON readings(room_id)
        """)
        # 兼容旧数据库：若列不存在则添加
        cols = [r[1] for r in self._db.execute("PRAGMA table_info(readings)").fetchall()]
        if "room_name" not in cols:
            self._db.execute("ALTER TABLE readings ADD COLUMN room_name TEXT NOT NULL DEFAULT ''")
        if "building_name" not in cols:
            self._db.execute("ALTER TABLE readings ADD COLUMN building_name TEXT NOT NULL DEFAULT ''")
        self._db.commit()

    def insert_reading(self, data: dict):
        self._db.execute(
            """INSERT INTO readings
               (timestamp, remaining_kwh, total_kwh, used_kwh,
                room_id, room_name, building_id, building_name, campus_id, raw_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now().isoformat(timespec="seconds"),
                data["remaining_kwh"],
                data["total_kwh"],
                data["used_kwh"],
                data["room_id"],
                data.get("room_name", ""),
                data["building_id"],
                data.get("building_name", ""),
                data["campus_id"],
                json.dumps(data.get("raw"), ensure_ascii=False),
            ),
        )
        self._db.commit()

    def get_latest(self) -> dict | None:
        row = self._db.execute(
            "SELECT * FROM readings ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def get_latest_per_room(self, building_id: str = None) -> list[dict]:
        """每个房间最新一条记录，可按楼栋筛选"""
        if building_id:
            rows = self._db.execute("""
                SELECT r.* FROM readings r
                INNER JOIN (
                    SELECT room_id, MAX(timestamp) AS ts FROM readings WHERE building_id = ? GROUP BY room_id
                ) latest ON r.room_id = latest.room_id AND r.timestamp = latest.ts
                ORDER BY r.room_id
            """, (building_id,)).fetchall()
        else:
            rows = self._db.execute("""
                SELECT r.* FROM readings r
                INNER JOIN (
                    SELECT room_id, MAX(timestamp) AS ts FROM readings GROUP BY room_id
                ) latest ON r.room_id = latest.room_id AND r.timestamp = latest.ts
                ORDER BY r.room_id
            """).fetchall()
        return [dict(r) for r in rows]

    def get_readings(self, days: int = 7, room_id: str = None) -> list[dict]:
        since = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        if room_id:
            rows = self._db.execute(
                "SELECT * FROM readings WHERE timestamp >= ? AND room_id = ? ORDER BY timestamp",
                (since, room_id),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM readings WHERE timestamp >= ? ORDER BY timestamp",
                (since,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_all_readings(self, room_id: str = None) -> list[dict]:
        if room_id:
            rows = self._db.execute(
                "SELECT * FROM readings WHERE room_id = ? ORDER BY timestamp",
                (room_id,),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM readings ORDER BY timestamp"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_daily_usage(self, days: int = 30, room_id: str = None) -> list[dict]:
        """计算每日用电量（当天第一条和最后一条的差值）"""
        readings = self.get_readings(days, room_id=room_id)
        if not readings:
            return []

        daily = {}
        for r in readings:
            date = r["timestamp"][:10]
            if date not in daily:
                daily[date] = {"first": r["remaining_kwh"], "last": r["remaining_kwh"]}
            else:
                daily[date]["last"] = r["remaining_kwh"]

        return [
            {"date": date, "usage": round(vals["first"] - vals["last"], 2)}
            for date, vals in sorted(daily.items())
            if vals["first"] - vals["last"] >= 0
        ]

    def get_rooms(self, building_id: str = None) -> list[dict]:
        """返回数据库中所有出现过的房间列表，可按楼栋筛选"""
        if building_id:
            rows = self._db.execute(
                "SELECT DISTINCT room_id, room_name, building_id, building_name FROM readings WHERE building_id = ? ORDER BY room_id",
                (building_id,),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT DISTINCT room_id, room_name, building_id, building_name FROM readings ORDER BY room_id"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_buildings(self) -> list[dict]:
        """返回数据库中所有出现过的楼栋列表"""
        rows = self._db.execute(
            "SELECT DISTINCT building_id, building_name FROM readings ORDER BY building_id"
        ).fetchall()
        return [dict(r) for r in rows]
