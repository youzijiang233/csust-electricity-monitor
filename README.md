# 长沙理工大学电费自动查询记录

自动从学校网站查询宿舍电费余额，定时记录数据，并提供 Web 仪表盘查看历史趋势。

## 功能

- 通过统一身份认证自动登录，无需手动操作
- 每天固定时间点自动查询（可配置），支持控制台手动触发
- 支持多楼栋、多宿舍批量查询，请求间隔可配置
- 数据存储到本地 SQLite 数据库
- Web 仪表盘：
  - 按楼栋/宿舍筛选，浏览器 cookie 记住上次选择
  - 电量趋势折线图、每日用电量柱状图
  - 楼栋内所有宿舍当前电量对比图（当前宿舍红色高亮）
  - 历史数据表格，支持按宿舍或全量导出 CSV / Excel

## 快速开始

**1. 安装依赖**

```bash
pip install -r requirements.txt
```

**2. 修改配置**

```bash
cp config.example.yaml config.yaml
```

编辑 `config.yaml`，填入学号和统一身份认证密码：

```yaml
auth:
  username: "学号"
  password: "统一身份认证密码"
```

**3. 添加楼栋数据**

将楼栋宿舍 json 文件放入 `buildings/` 目录，文件名格式为：

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

**4. 启动**

```bash
python main.py
```

打开浏览器访问 `http://localhost:5000`

**5. 手动触发查询**

程序启动后在终端输入指令：

```
query   # 立即查询所有宿舍
exit    # 退出程序
```

或通过 API 触发：

```bash
curl -X POST http://localhost:5000/api/trigger_query
```
或者用 PowerShell
```bash
Invoke-WebRequest -Method POST http://localhost:5000/api/trigger_query
```

---

## Docker 部署

**1. 使用预构建镜像**

```bash
docker pull youzijiang/electricity-monitor:latest
```

**2. 准备配置文件和楼栋数据**

```bash
cp config.example.yaml config.yaml
# 编辑 config.yaml 填入学号和密码
```

**3. 启动**

```bash
docker compose up -d
```

**4. 制作镜像（开发者）**

```bash
docker build -t youzijiang/electricity-monitor:latest .
docker push youzijiang/electricity-monitor:latest
```

---

## 配置说明

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `server.port` | Web 服务端口 | 5000 |
| `schedule.query_hours` | 每天查询的时间点列表 | [0,2,4,...,22] |
| `schedule.start_immediately` | 启动时立即查询一次 | false |
| `rooms.buildings_dir` | 楼栋 json 文件目录 | buildings |
| `rooms.query_interval_ms` | 每次请求间隔（毫秒） | 2000 |
| `database.path` | 数据库文件路径 | electricity.db |

## 项目结构

```
├── main.py               # 入口
├── auth.py               # CAS 统一身份认证登录
├── query.py              # 电费 API 查询
├── db.py                 # 数据库操作
├── scheduler.py          # 定时调度
├── web.py                # Web 仪表盘后端
├── export.py             # CSV/Excel 导出
├── buildings/            # 楼栋宿舍数据（楼栋名_楼栋id.json）
├── templates/
│   └── index.html        # 仪表盘页面
├── config.yaml           # 配置文件（不提交到 Git）
├── config.example.yaml   # 配置模板
└── requirements.txt
```
