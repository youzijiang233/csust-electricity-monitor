#!/bin/sh
set -e

DATA_DIR="/data"
CONFIG="$DATA_DIR/config.yaml"
BUILDINGS="$DATA_DIR/buildings"

# 首次启动：生成配置文件和示例楼栋数据
if [ ! -f "$CONFIG" ]; then
    echo ">>> 首次启动，正在初始化配置..."
    cp /app/config.example.yaml "$CONFIG"
    if [ ! -d "$BUILDINGS" ] || [ -z "$(ls -A $BUILDINGS 2>/dev/null)" ]; then
        mkdir -p "$BUILDINGS"
        cp /app/buildings/* "$BUILDINGS/" 2>/dev/null || true
    fi
    echo ">>> 配置文件已生成：$CONFIG"
    echo ">>> 请编辑配置文件，填入学号和密码，然后重新启动容器"
    exit 0
fi

# 检查是否还是默认占位符
if grep -q "你的学号\|你的统一身份认证密码" "$CONFIG"; then
    echo ">>> 检测到配置文件未填写账号密码，请编辑 $CONFIG 后重新启动容器"
    echo ">>> Web 服务已启动，填写完毕后执行 docker restart <容器名> 生效"
fi

# 升级兼容：检查 config.example.yaml 中有而用户 config.yaml 中缺少的顶级字段
ADDED=0
for key in $(grep -E '^[a-z]' /app/config.example.yaml | sed 's/:.*//' ); do
    if ! grep -q "^$key:" "$CONFIG"; then
        echo "" >> "$CONFIG"
        echo "# 升级自动补充" >> "$CONFIG"
        sed -n "/^$key:/,/^[a-z]/{ /^[a-z][^$key]/!p }" /app/config.example.yaml >> "$CONFIG"
        echo ">>> 新配置项 '$key' 已自动补充到 $CONFIG，请检查"
        ADDED=1
    fi
done

# 升级兼容：检查各顶级字段下的子字段是否缺失
while IFS= read -r line; do
    # 匹配形如 "  key: value" 的子字段行（2空格缩进，非注释）
    if echo "$line" | grep -qE '^  [a-z_]+:'; then
        subkey=$(echo "$line" | sed 's/^ *//' | sed 's/:.*//')
        # 在用户 config 中查找该子字段（只要出现过即认为存在）
        if ! grep -q "^\s*${subkey}:" "$CONFIG"; then
            # 找到这个子字段属于哪个顶级字段，追加到用户 config 对应块后面
            parent=$(grep -B 20 "^  ${subkey}:" /app/config.example.yaml | grep -E '^[a-z]' | tail -1 | sed 's/:.*//')
            if [ -n "$parent" ] && grep -q "^${parent}:" "$CONFIG"; then
                # 在用户 config 中找到父块末尾行号，追加子字段
                echo "  ${subkey}: $(echo "$line" | sed 's/^[^:]*: *//')" >> "$CONFIG"
                echo ">>> 新子配置项 '${parent}.${subkey}' 已自动补充到 $CONFIG，请检查"
                ADDED=1
            fi
        fi
    fi
done < /app/config.example.yaml

[ $ADDED -eq 1 ] && echo ">>> 配置已更新，建议检查 $CONFIG"

# buildings 目录为空时补充示例数据
if [ ! -d "$BUILDINGS" ] || [ -z "$(ls -A $BUILDINGS 2>/dev/null)" ]; then
    mkdir -p "$BUILDINGS"
    cp /app/buildings/* "$BUILDINGS/" 2>/dev/null || true
    echo ">>> buildings/ 目录为空，已复制示例楼栋数据"
fi

export DB_PATH="$DATA_DIR/electricity.db"
export BUILDINGS_DIR="$BUILDINGS"

exec python main.py
