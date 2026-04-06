"""Flask Web 仪表盘"""

from flask import Flask, jsonify, request, render_template, Response

from db import Database
from export import to_csv, to_excel


def create_app(db: Database, scheduler=None) -> Flask:
    app = Flask(__name__)

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
        if days <= 0:
            readings = db.get_all_readings(room_id=room_id)
        else:
            readings = db.get_readings(days, room_id=room_id)
        return jsonify(readings)

    @app.route("/api/daily_usage")
    def api_daily_usage():
        days = request.args.get("days", 30, type=int)
        room_id = request.args.get("room_id", None)
        return jsonify(db.get_daily_usage(days, room_id=room_id))

    @app.route("/api/trigger_query", methods=["POST"])
    def api_trigger_query():
        if not scheduler:
            return jsonify({"error": "scheduler not available"}), 503
        import threading
        threading.Thread(target=scheduler._query_and_store, daemon=True).start()
        return jsonify({"status": "started"})
        status = {
            "next_run": scheduler.get_next_run() if scheduler else "",
            "last_error": scheduler.last_error if scheduler else None,
        }
        return jsonify(status)

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
