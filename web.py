"""Flask Web 仪表盘"""

import gzip
from datetime import datetime, timedelta

from flask import Flask, jsonify, request, render_template, Response

from db import Database
from export import to_csv, to_excel


def _calc_next_run(query_hours: list[int]) -> str:
    now = datetime.now()
    hours = sorted(query_hours)
    for h in hours:
        candidate = now.replace(hour=h, minute=0, second=0, microsecond=0)
        if candidate > now:
            return candidate.strftime("%Y-%m-%dT%H:%M:%S")
    # 今天没有了，取明天第一个
    tomorrow = now + timedelta(days=1)
    candidate = tomorrow.replace(hour=hours[0], minute=0, second=0, microsecond=0)
    return candidate.strftime("%Y-%m-%dT%H:%M:%S")


def create_app(db: Database, scheduler=None, config: dict = None) -> Flask:
    app = Flask(__name__)

    @app.after_request
    def _gzip(response: Response) -> Response:
        # 仅压缩客户端支持 gzip、体积够大、尚未编码的文本类响应
        accept = request.headers.get("Accept-Encoding", "")
        if (
            "gzip" not in accept.lower()
            or response.direct_passthrough
            or response.status_code < 200
            or response.status_code >= 300
            or "Content-Encoding" in response.headers
            or response.content_length is None
            or response.content_length < 500
        ):
            return response
        ctype = response.content_type or ""
        if not (ctype.startswith("application/json") or ctype.startswith("text/")):
            return response
        compressed = gzip.compress(response.get_data(), compresslevel=6)
        response.set_data(compressed)
        response.headers["Content-Encoding"] = "gzip"
        response.headers["Content-Length"] = len(compressed)
        response.headers.add("Vary", "Accept-Encoding")
        return response

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/latest")
    def api_latest():
        latest = db.get_latest()
        return jsonify(latest or {})

    @app.route("/api/latest_per_room")
    def api_latest_per_room():
        building_id = request.args.get("building_id", None)
        return jsonify(db.get_latest_per_room(building_id=building_id))

    @app.route("/api/rooms")
    def api_rooms():
        building_id = request.args.get("building_id", None)
        return jsonify(db.get_rooms(building_id=building_id))

    @app.route("/api/buildings")
    def api_buildings():
        """返回所有楼栋列表（从数据库已有记录中提取）"""
        rows = db.get_buildings()
        return jsonify(rows)

    @app.route("/api/readings")
    def api_readings():
        days = request.args.get("days", 7, type=int)
        room_id = request.args.get("room_id", None)
        page = request.args.get("page", None, type=int)
        page_size = request.args.get("page_size", 20, type=int)
        # 趋势图只需要 timestamp + remaining_kwh，避免传输庞大的 raw_json
        cols = "timestamp, remaining_kwh" if request.args.get("fields") == "trend" else "*"
        if page is not None:
            return jsonify(db.get_readings_paged(page=page, page_size=page_size, room_id=room_id, days=days))
        if days <= 0:
            readings = db.get_all_readings(room_id=room_id, columns=cols)
        else:
            readings = db.get_readings(days, room_id=room_id, columns=cols)
        return jsonify(readings)

    @app.route("/api/daily_usage")
    def api_daily_usage():
        days = request.args.get("days", 30, type=int)
        room_id = request.args.get("room_id", None)
        return jsonify(db.get_daily_usage(days, room_id=room_id))

    @app.route("/api/usage_per_room")
    def api_usage_per_room():
        days = request.args.get("days", 1, type=int)
        building_id = request.args.get("building_id", None)
        return jsonify(db.get_usage_per_room(days=days, building_id=building_id))

    @app.route("/api/trigger_query", methods=["POST"])
    def api_trigger_query():
        if not scheduler:
            return jsonify({"error": "scheduler not available"}), 503
        import threading
        threading.Thread(target=scheduler._query_and_store, daemon=True).start()
        return jsonify({"status": "started"})

    @app.route("/api/status")
    def api_status():
        query_hours = (config or {}).get("schedule", {}).get("query_hours", [])
        next_run = _calc_next_run(query_hours) if query_hours else ""
        return jsonify({
            "next_run": next_run,
            "last_error": scheduler.last_error if scheduler else None,
            "trend_yaxis": (config or {}).get("dashboard", {}).get("trend_yaxis", "adaptive"),
        })

    @app.route("/api/export")
    def api_export():
        fmt = request.args.get("format", "csv")
        days = request.args.get("days", 0, type=int)
        room_id = request.args.get("room_id", None)
        readings = db.get_all_readings(room_id=room_id) if days <= 0 else db.get_readings(days, room_id=room_id)

        if fmt == "excel":
            data = to_excel(readings)
            return Response(
                data,
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": "attachment; filename=electricity.xlsx"},
            )
        else:
            data = to_csv(readings)
            return Response(
                data,
                mimetype="text/csv",
                headers={"Content-Disposition": "attachment; filename=electricity.csv"},
            )

    return app
