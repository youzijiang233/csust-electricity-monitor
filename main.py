"""长沙理工大学电费自动查询记录 - 入口"""

import logging
import os
import threading
import yaml

from auth import TokenManager
from db import Database
from scheduler import ElectricityScheduler
from web import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def apply_env_overrides(config: dict):
    """用环境变量覆盖敏感配置，方便 Docker 部署"""
    if os.environ.get("AUTH_USERNAME"):
        config["auth"]["username"] = os.environ["AUTH_USERNAME"]
    if os.environ.get("AUTH_PASSWORD"):
        config["auth"]["password"] = os.environ["AUTH_PASSWORD"]
    if os.environ.get("DB_PATH"):
        config["database"]["path"] = os.environ["DB_PATH"]


def console_loop(sched: ElectricityScheduler):
    print("控制台就绪，输入 'query' 立即查询，输入 'exit' 退出")
    while True:
        try:
            cmd = input().strip().lower()
        except EOFError:
            break
        if cmd == "query":
            threading.Thread(target=sched._query_and_store, daemon=True).start()
        elif cmd == "exit":
            import os; os._exit(0)
        else:
            print("未知指令，可用指令: query / exit")


def main():
    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    apply_env_overrides(config)

    db = Database(config["database"]["path"])
    token_manager = TokenManager(config)
    sched = ElectricityScheduler(config, db, token_manager)

    sched.start()

    app = create_app(db, sched, config)
    host = config["server"]["host"]
    port = config["server"]["port"]

    logger.info("仪表盘地址: http://localhost:%d", port)

    threading.Thread(target=console_loop, args=(sched,), daemon=True).start()

    from waitress import serve
    serve(app, host=host, port=port)


if __name__ == "__main__":
    main()
