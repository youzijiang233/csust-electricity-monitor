# 长沙理工大学电费自动查询记录

自动从学校网站查询宿舍电费余额，定时记录数据，并提供 Web 仪表盘查看历史趋势。

## 功能

- 通过统一身份认证自动登录，无需手动操作
- 每小时自动查询一次（可配置），支持控制台手动触发
- 支持多楼栋、多宿舍批量查询，请求间隔可配置
- 数据存储到本地 SQLite 数据库
- Web 仪表盘：
  - 按楼栋/宿舍筛选，浏览器 cookie 记住上次选择
  - 电量趋势折线图、每日用电量柱状图
  - 楼栋内所有宿舍电量对比图，支持切换查看当前电量、今日用电、7天用电（当前宿舍红色高亮）
  - 当前剩余电量与近24小时用电量并排展示
  - 历史数据表格后端分页，支持按宿舍或全量导出 CSV / Excel

---

## Docker 部署（推荐）

无需克隆代码，直接拉取镜像运行。

**1. 首次启动，自动生成配置文件**

```bash
mkdir csust-electricity-monitor && cd csust-electricity-monitor
docker run --rm -v ./data:/data youzijiang/csust-electricity-monitor:latest
```

容器会在 `./data/` 目录下生成 `config.yaml` 和示例 `buildings/`，然后自动退出并提示你编辑配置。

**2. 编辑配置，填入学号和密码**

```bash
nano data/config.yaml
```

```yaml
auth:
  username: "你的学号"
  password: "你的统一身份认证密码"
```

**4. 添加楼栋数据**

将楼栋宿舍 json 文件放入 `data/buildings/` 目录，文件名格式：

```
楼栋名_楼栋id.json
```

例如：`至诚轩5栋A区_557.json`，json 格式：

```json
{
  "map": {
    "data": [
      { "name": "A101", "value": "49000" },
      { "name": "A102", "value": "49001" }
    ]
  }
}
```

**5. 正式启动**

```bash
docker run -d \
  -v ./data:/data \
  -p 5000:5000 \
  -e TZ=Asia/Shanghai \
  --restart unless-stopped \
  --name csust-electricity-monitor \
  youzijiang/csust-electricity-monitor:latest
```

打开浏览器访问 `http://服务器IP:5000`

**6. 查看日志**

```bash
docker logs -f csust-electricity-monitor
```

**升级镜像**

```bash
docker stop csust-electricity-monitor && docker rm csust-electricity-monitor
docker pull youzijiang/csust-electricity-monitor:latest
docker run -d \
  -v ./data:/data \
  -p 5000:5000 \
  -e TZ=Asia/Shanghai \
  --restart unless-stopped \
  --name csust-electricity-monitor \
  youzijiang/csust-electricity-monitor:latest
```

---

## 本地运行

**1. 安装依赖**

```bash
pip install -r requirements.txt
```

**2. 修改配置**

```bash
cp config.example.yaml config.yaml
```

编辑 `config.yaml`，填入学号和统一身份认证密码。

**3. 添加楼栋数据**

将楼栋 json 文件放入 `buildings/` 目录（格式同上）。

**4. 启动**

```bash
python main.py
```

打开浏览器访问 `http://localhost:5000`

**5. 手动触发查询**

程序启动后在终端输入：

```
query   # 立即查询所有宿舍
exit    # 退出程序
```

或通过 API 触发：

```bash
# Linux/macOS
curl -X POST http://localhost:5000/api/trigger_query

# Windows PowerShell
Invoke-WebRequest -Method POST http://localhost:5000/api/trigger_query
```

---

## 配置说明

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `server.port` | Web 服务端口 | 5000 |
| `schedule.query_hours` | 每天查询的时间点列表 | 每小时一次 |
| `schedule.start_immediately` | 启动时立即查询一次 | false |
| `rooms.buildings_dir` | 楼栋 json 文件目录 | buildings |
| `rooms.query_interval_ms` | 每次请求间隔（毫秒） | 2000 |
| `database.path` | 数据库文件路径 | electricity.db |

Docker 部署时 `buildings_dir` 和 `database.path` 由容器自动设置，无需手动修改。

---

## 项目结构

```
├── main.py               # 入口
├── auth.py               # CAS 统一身份认证登录
├── query.py              # 电费 API 查询
├── db.py                 # 数据库操作
├── scheduler.py          # 定时调度
├── web.py                # Web 仪表盘后端
├── export.py             # CSV/Excel 导出
├── entrypoint.sh         # Docker 启动脚本
├── buildings/            # 楼栋宿舍数据（楼栋名_楼栋id.json）
├── templates/
│   └── index.html        # 仪表盘页面
├── config.yaml           # 配置文件（不提交到 Git）
├── config.example.yaml   # 配置模板
└── requirements.txt
```
