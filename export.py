"""CSV/Excel 数据导出"""

import csv
import io
from openpyxl import Workbook


HEADERS = ["时间", "剩余电量(kWh)", "总电量(kWh)", "已用电量(kWh)", "房间ID", "楼栋ID", "校区ID"]
FIELDS = ["timestamp", "remaining_kwh", "total_kwh", "used_kwh", "room_id", "building_id", "campus_id"]


def to_csv(readings: list[dict]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(HEADERS)
    for r in readings:
        writer.writerow([r.get(f, "") for f in FIELDS])
    return buf.getvalue().encode("utf-8-sig")


def to_excel(readings: list[dict]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "电费记录"
    ws.append(HEADERS)
    for r in readings:
        ws.append([r.get(f, "") for f in FIELDS])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
