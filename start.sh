#!/usr/bin/env bash
# 三格电 一键启动：后端 uvicorn(:8000) + 前端 vite(:5173)
# 用法：
#   ./start.sh          # 前台运行（Ctrl+C 一起停）
#   ./start.sh -d       # 后台运行（日志 /tmp/dobby-*.log）
#   ./start.sh stop     # 停止运行中的实例
#   ./start.sh status   # 查看运行状态
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "$0")" && pwd)
cd "$ROOT_DIR"

BACKEND_LOG=/tmp/dobby-backend.log
FRONTEND_LOG=/tmp/dobby-frontend.log
BACKEND_PID=/tmp/dobby-backend.pid
FRONTEND_PID=/tmp/dobby-frontend.pid

LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "本机IP")

log()  { printf "\033[32m[dobby]\033[0m %s\n" "$*"; }
warn() { printf "\033[33m[dobby]\033[0m %s\n" "$*"; }

listeners() { lsof -ti :"$1" -sTCP:LISTEN 2>/dev/null || true; }

# 数据库可写性探针：端口活着 ≠ 数据库能写（曾出现迁移后进程僵死、写报 readonly/locked 的坑）
db_healthy() {
  .venv/bin/python - <<'PY' 2>/dev/null
import sqlite3, sys
DB = 'server/data/app.db'
try:
    c = sqlite3.connect(DB)
    c.execute('BEGIN IMMEDIATE')
    c.rollback()
    sys.exit(0)
except Exception:
    sys.exit(1)
PY
}

do_stop() {
  for pidfile in "$BACKEND_PID" "$FRONTEND_PID"; do
    if [ -f "$pidfile" ]; then
      kill "$(cat "$pidfile")" 2>/dev/null || true
      rm -f "$pidfile"
    fi
  done
  # npm 是中间进程，杀它不会带走 vite(node)；直接杀端口上的 LISTEN 进程
  for port in 8000 5173; do
    local pids; pids=$(listeners "$port")
    [ -n "$pids" ] && kill $pids 2>/dev/null || true
  done
  log "已停止"
}

case "${1:-run}" in
  stop)
    do_stop
    exit 0 ;;
  status)
    for pair in "8000:后端" "5173:前端"; do
      port=${pair%%:*}; name=${pair##*:}
      if [ -n "$(listeners "$port")" ]; then
        log "$name 运行中 (端口 $port)"
        if [ "$port" = "8000" ]; then
          if db_healthy; then
            log "  数据库可写：健康"
          else
            warn "  数据库不可写：进程疑似僵死，建议 ./start.sh stop && ./start.sh -d"
          fi
        fi
      else
        warn "$name 未运行"
      fi
    done
    exit 0 ;;
esac

# 端口占用检查（只看 LISTEN；浏览器打开页面产生的连接不算占用）
for port in 8000 5173; do
  if [ -n "$(listeners "$port")" ]; then
    warn "端口 $port 已被占用（可能是之前的实例）："
    lsof -i :"$port" -sTCP:LISTEN
    warn "如需重启，先执行：./start.sh stop"
    exit 1
  fi
done

if [ "${1:-run}" = "-d" ]; then
  # 后台模式
  nohup .venv/bin/uvicorn server.main:app --host 0.0.0.0 --port 8000 > "$BACKEND_LOG" 2>&1 &
  echo $! > "$BACKEND_PID"
  (cd web && nohup npm run dev > "$FRONTEND_LOG" 2>&1 & echo $! > "$FRONTEND_PID")
  sleep 2
  log "后台启动完成：后端日志 ${BACKEND_LOG}，前端日志 ${FRONTEND_LOG}"
  log "iPhone 访问：http://${LAN_IP}:5173"
else
  # 前台模式：vite 跟随终端；Ctrl+C 同时停掉后端
  .venv/bin/uvicorn server.main:app --host 0.0.0.0 --port 8000 > "$BACKEND_LOG" 2>&1 &
  BACKEND_FG=$!
  trap 'kill "$BACKEND_FG" 2>/dev/null; exit 0' INT TERM
  log "iPhone 访问：http://${LAN_IP}:5173（后端日志 $BACKEND_LOG）"
  (cd web && exec npm run dev)
fi
