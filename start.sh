#!/bin/bash

# OpenClaw 团队信息看板启动脚本
# 版本: 1.0
# 创建: 2026-03-18

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# 项目根目录
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_V2_DIR="$PROJECT_DIR/frontend-v2"
CRAWLER_DIR="${CRAWLER_DIR:-$HOME/.openclaw/tools/crawl4ai-runtime}"
CRAWLER_PORT="${CRAWLER_PORT:-11235}"
JWT_SECRET_FILE="$BACKEND_DIR/data/.dashboard_jwt_secret"
DEFAULT_DATABASE_URL="sqlite:///$BACKEND_DIR/data/dashboard_v2.db"

if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

# 默认配置
API_PORT="${API_PORT:-3021}"
LEGACY_API_PORT="${LEGACY_API_PORT:-3020}"
FRONTEND_ENTRY="${FRONTEND_ENTRY:-index.html}"
USE_FRONTEND_V2="${USE_FRONTEND_V2:-true}"
DISABLE_SCHEDULER="${DISABLE_SCHEDULER:-false}"
DATABASE_URL="${DATABASE_URL:-$DEFAULT_DATABASE_URL}"
AI_PLANNING_TUNNEL_ENABLED="${AI_PLANNING_TUNNEL_ENABLED:-true}"
AI_PLANNING_TUNNEL_PORT="${AI_PLANNING_TUNNEL_PORT:-15130}"
AI_PLANNING_REMOTE_HOST="${AI_PLANNING_REMOTE_HOST:-192.168.31.144}"
AI_PLANNING_REMOTE_PORT="${AI_PLANNING_REMOTE_PORT:-5130}"
AI_PLANNING_REMOTE_USER="${AI_PLANNING_REMOTE_USER:-sunyi}"
AI_PLANNING_BASE_URL="${AI_PLANNING_BASE_URL:-http://127.0.0.1:$AI_PLANNING_TUNNEL_PORT}"
AI_PLANNING_PUBLIC_URL="${AI_PLANNING_PUBLIC_URL:-http://$AI_PLANNING_REMOTE_HOST:$AI_PLANNING_REMOTE_PORT}"

# 打印带颜色的信息
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${CYAN}${BOLD}"
    echo "╔════════════════════════════════════════════════════════╗"
    echo "║     🤖 OpenClaw 团队信息看板启动脚本                  ║"
    echo "╚════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# 检查端口是否被占用
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 1
    else
        return 0
    fi
}

# 查找占用端口的进程并杀死
kill_port() {
    local port=$1
    local pid=$(lsof -Pi :$port -sTCP:LISTEN -t 2>/dev/null)
    if [ ! -z "$pid" ]; then
        print_warning "端口 $port 被占用 (PID: $pid)，正在终止..."
        kill -9 $pid 2>/dev/null
        sleep 1
    fi
}

# 检查 Python 环境
check_python() {
    if ! command -v python3 &> /dev/null; then
        print_error "未找到 Python3，请先安装 Python 3.x"
        exit 1
    fi
    print_success "Python3 已安装: $(python3 --version)"
}

# 检查虚拟环境
check_venv() {
    if [ ! -d "$BACKEND_DIR/venv" ]; then
        print_warning "未找到虚拟环境，正在创建..."
        cd "$BACKEND_DIR" && python3 -m venv venv
        print_success "虚拟环境创建完成"
    fi
    
    print_info "正在激活虚拟环境..."
    source "$BACKEND_DIR/venv/bin/activate"
    
    # 检查依赖
    if ! pip list | grep -q "fastapi"; then
        print_warning "正在安装依赖..."
        pip install fastapi uvicorn pydantic -q
        print_success "依赖安装完成"
    fi
}

ensure_jwt_secret() {
    mkdir -p "$BACKEND_DIR/data"
    if [ ! -f "$JWT_SECRET_FILE" ]; then
        "$BACKEND_DIR/venv/bin/python" -c 'import secrets; print(secrets.token_urlsafe(48))' > "$JWT_SECRET_FILE"
        chmod 600 "$JWT_SECRET_FILE"
    fi
    export DASHBOARD_JWT_SECRET="$(cat "$JWT_SECRET_FILE")"
}

start_crawler() {
    local crawler_python="$CRAWLER_DIR/venv/bin/python"
    local crawler_uvicorn="$CRAWLER_DIR/venv/bin/uvicorn"
    local crawler_server="$CRAWLER_DIR/server.py"
    if [ ! -x "$crawler_python" ] || [ ! -x "$crawler_uvicorn" ] || [ ! -f "$crawler_server" ]; then
        print_warning "Crawl4AI 运行环境未安装，网络采集工具暂不可用"
        return
    fi
    if curl -fsS "http://127.0.0.1:$CRAWLER_PORT/health" >/dev/null 2>&1; then
        print_success "Crawl4AI 网络采集服务已运行"
        return
    fi
    if ! check_port "$CRAWLER_PORT"; then
        kill_port "$CRAWLER_PORT"
    fi
    print_info "启动 Crawl4AI 网络采集服务 (本机端口: $CRAWLER_PORT)..."
    cd "$CRAWLER_DIR"
    nohup "$crawler_uvicorn" server:app --host 127.0.0.1 --port "$CRAWLER_PORT" > crawler.log 2>&1 &
    for i in {1..15}; do
        if curl -fsS "http://127.0.0.1:$CRAWLER_PORT/health" >/dev/null 2>&1; then
            print_success "Crawl4AI 网络采集服务启动成功"
            return
        fi
        sleep 1
    done
    print_warning "Crawl4AI 启动失败，请检查 $CRAWLER_DIR/crawler.log"
}

start_ai_planning_tunnel() {
    if [ "$AI_PLANNING_TUNNEL_ENABLED" != "true" ]; then
        print_info "5130 本地端口转发已禁用，使用 $AI_PLANNING_BASE_URL"
        return
    fi
    if curl -fsS "$AI_PLANNING_BASE_URL/openapi.json" >/dev/null 2>&1; then
        print_success "5130 本地端口转发已运行"
        return
    fi
    if ! check_port "$AI_PLANNING_TUNNEL_PORT"; then
        kill_port "$AI_PLANNING_TUNNEL_PORT"
    fi
    print_info "建立本地 $AI_PLANNING_TUNNEL_PORT -> $AI_PLANNING_REMOTE_HOST:$AI_PLANNING_REMOTE_PORT 端口转发..."
    ssh -f -N \
        -o BatchMode=yes \
        -o ExitOnForwardFailure=yes \
        -o ServerAliveInterval=30 \
        -o ServerAliveCountMax=3 \
        -o StrictHostKeyChecking=no \
        -L "$AI_PLANNING_TUNNEL_PORT:127.0.0.1:$AI_PLANNING_REMOTE_PORT" \
        "$AI_PLANNING_REMOTE_USER@$AI_PLANNING_REMOTE_HOST"
    for i in {1..8}; do
        if curl -fsS "$AI_PLANNING_BASE_URL/openapi.json" >/dev/null 2>&1; then
            print_success "5130 本地端口转发建立成功"
            return
        fi
        sleep 1
    done
    print_warning "5130 本地端口转发未就绪，产品集成会明确显示离线"
}

# 启动后端服务
start_backend() {
    print_header
    print_info "项目目录: $PROJECT_DIR"
    echo ""
    
    # 检查环境
    check_python
    check_venv
    start_crawler
    start_ai_planning_tunnel
    
    echo ""
    print_info "准备启动后端服务..."
    
    # 检查并清理端口
    if ! check_port $API_PORT; then
        kill_port $API_PORT
    fi
    if [ "$LEGACY_API_PORT" != "$API_PORT" ] && ! check_port $LEGACY_API_PORT; then
        print_warning "检测到旧 3020 服务，归并到 $API_PORT 前先停止旧入口..."
        kill_port $LEGACY_API_PORT
    fi
    
    # 启动后端
    cd "$BACKEND_DIR"
    ensure_jwt_secret
    export FRONTEND_ENTRY="$FRONTEND_ENTRY"
    export USE_FRONTEND_V2="$USE_FRONTEND_V2"
    export API_PORT="$API_PORT"
    export DISABLE_SCHEDULER="$DISABLE_SCHEDULER"
    export DATABASE_URL="$DATABASE_URL"
    export AI_PLANNING_BASE_URL="$AI_PLANNING_BASE_URL"
    export AI_PLANNING_PUBLIC_URL="$AI_PLANNING_PUBLIC_URL"
    if [ "$USE_FRONTEND_V2" = "true" ]; then
        print_info "前端入口: frontend-v2/dist/index.html"
    else
        print_info "前端入口文件: $FRONTEND_ENTRY"
    fi
    print_info "启动 FastAPI 服务 (端口: $API_PORT)..."
    
    # 使用 nohup 在后台运行
    nohup ./venv/bin/uvicorn main_slim_v2:app --host 0.0.0.0 --port "$API_PORT" > backend-slim-3021.log 2>&1 &
    BACKEND_PID=$!
    
    # 等待服务启动
    print_info "等待服务启动..."
    for i in {1..10}; do
        if check_port $API_PORT; then
            sleep 1
            if curl -s http://localhost:$API_PORT/ > /dev/null 2>&1; then
                print_success "后端服务启动成功！"
                break
            fi
        fi
        sleep 1
    done
    
    # 检查是否真正启动
    if ! curl -s http://localhost:$API_PORT/ > /dev/null 2>&1; then
        print_error "后端服务启动失败，请检查日志: $BACKEND_DIR/backend-slim-3021.log"
        exit 1
    fi
    
    echo ""
    print_success "✅ 后端服务运行中"
    print_info "   API 地址: http://localhost:$API_PORT"
    print_info "   API 文档: http://localhost:$API_PORT/docs"
    print_info "   日志文件: $BACKEND_DIR/backend-slim-3021.log"
    print_info "   进程 PID: $BACKEND_PID"
}

# 停止服务
stop_services() {
    print_header
    print_info "正在停止服务..."
    
    # 停止后端
    kill_port $API_PORT
    if [ "$LEGACY_API_PORT" != "$API_PORT" ]; then
        kill_port $LEGACY_API_PORT
    fi
    kill_port $CRAWLER_PORT
    if [ "$AI_PLANNING_TUNNEL_ENABLED" = "true" ]; then
        kill_port "$AI_PLANNING_TUNNEL_PORT"
    fi
    
    echo ""
    print_success "✅ 所有服务已停止"
}

# 查看状态
show_status() {
    print_header
    print_info "服务状态检查"
    echo ""
    
    # 检查后端
    if curl -s http://localhost:$API_PORT/ > /dev/null 2>&1; then
        print_success "后端服务: 运行中 ✓"
        print_info "   http://localhost:$API_PORT"
    else
        print_error "后端服务: 未运行 ✗"
    fi
    if curl -fsS "http://127.0.0.1:$CRAWLER_PORT/health" >/dev/null 2>&1; then
        print_success "网络采集服务: 运行中 ✓"
    else
        print_error "网络采集服务: 未运行 ✗"
    fi
    
    echo ""
    print_info "快速访问链接："
    echo "  - 看板首页: http://localhost:$API_PORT/"
    echo "  - API 根路径: http://localhost:$API_PORT/"
    echo "  - 智能体列表: http://localhost:$API_PORT/api/agents"
    echo "  - 任务列表: http://localhost:$API_PORT/api/tasks"
}

# 主菜单
show_menu() {
    print_header
    echo ""
    echo "  ${BOLD}可用命令:${NC}"
    echo ""
    echo "  ${GREEN}./start.sh${NC}         - 启动后端服务"
    echo "  ${GREEN}./start.sh all${NC}     - 启动 3021 统一服务"
    echo "  ${RED}./start.sh stop${NC}    - 停止所有服务"
    echo "  ${BLUE}./start.sh status${NC}  - 查看服务状态"
    echo "  ${YELLOW}./start.sh help${NC}    - 显示帮助信息"
    echo ""
}

# 帮助信息
show_help() {
    show_menu
    echo "${BOLD}项目信息:${NC}"
    echo "  - 后端框架: FastAPI + Python 3"
    echo "  - 前端框架: Vue 3 + Element Plus"
    echo "  - 数据可视化: ECharts"
    echo "  - API 端口: $API_PORT"
    echo "  - 前端入口: $FRONTEND_V2_DIR/dist/index.html"
    echo ""
    echo "${BOLD}文件位置:${NC}"
    echo "  - 后端代码: $BACKEND_DIR/main_slim_v2.py"
    echo "  - 前端代码: $FRONTEND_V2_DIR/src"
    echo "  - 后端日志: $BACKEND_DIR/backend-slim-3021.log"
    echo ""
}

# 主函数
main() {
    case "${1:-start}" in
        start|"")
            start_backend
            echo ""
            print_success "🎉 服务启动完成！"
            echo ""
            print_info "访问方式:"
            echo "  1. 看板首页: http://localhost:$API_PORT/"
            echo "  2. API 文档: http://localhost:$API_PORT/docs"
            echo ""
            print_info "API 端点:"
            echo "  - http://localhost:$API_PORT/api/agents"
            echo "  - http://localhost:$API_PORT/api/tasks"
            echo "  - http://localhost:$API_PORT/api/devices"
            echo ""
            print_info "按 Ctrl+C 停止日志输出，服务将在后台继续运行"
            print_info "使用 ./start.sh stop 停止所有服务"
            echo ""
            
            # 持续显示日志
            tail -f "$BACKEND_DIR/backend-slim-3021.log" 2>/dev/null || true
            ;;
        all)
            start_backend
            echo ""
            print_success "🎉 3021 统一服务启动完成！"
            echo ""
            print_info "访问地址:"
            echo "  🌐 OpenClaw: http://localhost:$API_PORT"
            echo "  📚 API 文档: http://localhost:$API_PORT/docs"
            echo ""

            # 持续显示日志
            tail -f "$BACKEND_DIR/backend-slim-3021.log" 2>/dev/null || true
            ;;
        stop)
            stop_services
            ;;
        status)
            show_status
            ;;
        help|-h|--help)
            show_help
            ;;
        *)
            print_error "未知命令: $1"
            show_menu
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@"
