#!/usr/bin/env bash
set -eu
if [ -n "${BASH_VERSION:-}" ]; then
  set -o pipefail
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
echo "$SCRIPT_DIR"

export PYTHONPATH="$SCRIPT_DIR"
export NO_PROXY="127.0.0.1,localhost"
export no_proxy="127.0.0.1,localhost"

LOG_DIR="$SCRIPT_DIR/data/logs"
mkdir -p "$LOG_DIR"
STARTUP_LOG="$LOG_DIR/startup.log"
BACKEND_PID_FILE="$LOG_DIR/backend.pid"
FRONTEND_PID_FILE="$LOG_DIR/frontend.pid"
BACKGROUND=1
STOP_ONLY=0

for arg in "$@"; do
  case "$arg" in
    --background|-d|--daemon)
      BACKGROUND=1
      ;;
    --foreground|-f)
      BACKGROUND=0
      ;;
    --stop|stop)
      STOP_ONLY=1
      ;;
    --help|-h)
      printf 'Usage: %s [--foreground|-f] [--stop|stop]\n' "$0"
      printf '  默认后台运行，加 -f 前台运行\n'
      exit 0
      ;;
    *)
      printf '未知参数: %s\n' "$arg" >&2
      printf 'Usage: %s [--foreground|-f] [--stop|stop]\n' "$0" >&2
      exit 2
      ;;
  esac
done

log() {
  local level="${2:-INFO}"
  local message="$1"
  printf '%s | %s | startup | %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$level" "$message" >> "$STARTUP_LOG"
  printf '%s\n' "$message"
}

find_python() {
  if [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
    printf '%s\n' "$SCRIPT_DIR/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  elif command -v python >/dev/null 2>&1; then
    command -v python
  else
    return 1
  fi
}

stop_port() {
  local port="$1"
  local pids=""

  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -ti tcp:"$port" 2>/dev/null || true)"
  elif command -v fuser >/dev/null 2>&1; then
    pids="$(fuser "$port"/tcp 2>/dev/null || true)"
  fi

  if [ -n "$pids" ]; then
    log "释放端口 $port (PID $pids)..."
    kill $pids 2>/dev/null || true
    sleep 1
  fi
}

stop_pid_file() {
  local pid_file="$1"
  local name="$2"
  local pid=""

  if [ ! -f "$pid_file" ]; then
    return 0
  fi

  pid="$(tr -d '[:space:]' < "$pid_file" || true)"
  rm -f "$pid_file"
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    log "停止 $name (PID $pid)..."
    kill "$pid" 2>/dev/null || true
  fi
}

stop_services() {
  stop_pid_file "$BACKEND_PID_FILE" "后端"
  stop_pid_file "$FRONTEND_PID_FILE" "前端"
  stop_port 8000
  stop_port 5173
}

wait_for_url() {
  local url="$1"
  local attempts="${2:-60}"
  local i
  local code

  for i in $(seq 1 "$attempts"); do
    if command -v curl >/dev/null 2>&1; then
      code="$(curl -sS -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || true)"
      case "$code" in
        2??|3??)
          return 0
          ;;
      esac
    fi
    sleep 1
  done

  return 1
}

wait_for_frontend() {
  local attempts="${1:-60}"
  local i
  local code
  local url

  for i in $(seq 1 "$attempts"); do
    for url in "http://127.0.0.1:5173/" "http://localhost:5173/" "http://0.0.0.0:5173/"; do
      if command -v curl >/dev/null 2>&1; then
        code="$(curl -sS -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || true)"
        case "$code" in
          2??|3??)
            return 0
            ;;
        esac
      fi
    done
    sleep 1
  done

  return 1
}

cleanup() {
  if [ "$BACKGROUND" = "1" ]; then
    return 0
  fi

  log "正在停止服务..."
  if [ -n "${BACKEND_PID:-}" ]; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  if [ -n "${FRONTEND_PID:-}" ]; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
  wait "${BACKEND_PID:-}" 2>/dev/null || true
  wait "${FRONTEND_PID:-}" 2>/dev/null || true
  rm -f "$BACKEND_PID_FILE" "$FRONTEND_PID_FILE"
  log "已停止"
}

trap cleanup EXIT INT TERM

if [ "$STOP_ONLY" = "1" ]; then
  stop_services
  log "已停止"
  exit 0
fi

stop_services

log "========================================"
log "   个人AI投研助手  开发环境启动器"
log "========================================"

PYTHON_BIN="$(find_python)" || {
  log "未找到 Python，请先安装 Python 3.10+" "ERROR"
  exit 1
}

if ! command -v node >/dev/null 2>&1; then
  log "未找到 Node.js，请先安装 Node.js 18+" "ERROR"
  exit 1
fi

if [ ! -f "$SCRIPT_DIR/.env" ]; then
  log "未找到 .env，请先复制 .env.example 为 .env 并填写本地配置" "ERROR"
  log "安装说明见 README.md"
  exit 1
fi

if ! "$PYTHON_BIN" -c "import fastapi, uvicorn" >/dev/null 2>&1; then
  log "未找到后端依赖，请先执行: python -m pip install -e '.[dev]'" "ERROR"
  log "安装说明见 README.md"
  exit 1
fi

if [ ! -f "$SCRIPT_DIR/web/node_modules/vite/bin/vite.js" ]; then
  log "未找到前端依赖，请先执行: cd web && npm install && cd .." "ERROR"
  log "安装说明见 README.md"
  exit 1
fi

log "[后端] 启动 FastAPI ..."
"$PYTHON_BIN" "$SCRIPT_DIR/main.py" > "$LOG_DIR/backend.out.log" 2> "$LOG_DIR/backend.err.log" &
BACKEND_PID=$!
printf '%s\n' "$BACKEND_PID" > "$BACKEND_PID_FILE"

sleep 2

log "[前端] 启动 React ..."
(
  cd "$SCRIPT_DIR/web"
  node "node_modules/vite/bin/vite.js" --host 0.0.0.0 --strictPort
) > "$LOG_DIR/frontend.log" 2> "$LOG_DIR/frontend.err.log" &
FRONTEND_PID=$!
printf '%s\n' "$FRONTEND_PID" > "$FRONTEND_PID_FILE"

log "等待服务启动 ..."

if wait_for_url "http://127.0.0.1:8000/docs" 20; then
  log "[成功] 后端已启动: http://127.0.0.1:8000/docs"
else
  log "[失败] 后端未响应" "ERROR"
  if [ -f "$LOG_DIR/backend.err.log" ]; then
    printf '%s\n' "--- backend.err.log (last 20 lines) ---"
    tail -n 20 "$LOG_DIR/backend.err.log"
  fi
fi

if wait_for_frontend 60; then
  log "[成功] 前端已启动: http://127.0.0.1:5173"
else
  log "[失败] 前端未响应" "ERROR"
  if [ -f "$LOG_DIR/frontend.err.log" ]; then
    printf '%s\n' "--- frontend.err.log (last 20 lines) ---"
    tail -n 20 "$LOG_DIR/frontend.err.log"
  fi
fi

if [ "$BACKGROUND" = "1" ]; then
  trap - EXIT INT TERM
  log "后台运行中。停止服务: sh $SCRIPT_DIR/start.sh --stop"
  log "日志目录: $LOG_DIR"
  exit 0
fi

log "按 Enter 键停止所有服务..."
read -r _
