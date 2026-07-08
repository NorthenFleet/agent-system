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
FRONTEND_DIR="$PROJECT_DIR/frontend"
JWT_SECRET_FILE="$BACKEND_DIR/data/.dashboard_jwt_secret"

if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

# 默认配置
API_PORT="${API_PORT:-3021}"
LEGACY_API_PORT="${LEGACY_API_PORT:-3020}"
FRONTEND_PORT=8080
FRONTEND_ENTRY="${FRONTEND_ENTRY:-index.html}"
USE_FRONTEND_V2="${USE_FRONTEND_V2:-true}"
DISABLE_SCHEDULER="${DISABLE_SCHEDULER:-false}"

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

# 启动后端服务
start_backend() {
    print_header
    print_info "项目目录: $PROJECT_DIR"
    echo ""
    
    # 检查环境
    check_python
    check_venv
    
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

# 启动前端（使用 Python 简单 HTTP 服务器）
start_frontend() {
    echo ""
    print_info "准备启动前端服务..."
    
    # 检查端口
    if ! check_port $FRONTEND_PORT; then
        kill_port $FRONTEND_PORT
    fi
    
    cd "$FRONTEND_DIR"
    
    # 使用 Python 启动简单 HTTP 服务器
    nohup python3 -m http.server $FRONTEND_PORT > frontend.log 2>&1 &
    FRONTEND_PID=$!
    
    sleep 2
    
    if check_port $FRONTEND_PORT; then
        print_success "✅ 前端服务启动成功！"
        print_info "   访问地址: http://localhost:$FRONTEND_PORT"
        print_info "   日志文件: $FRONTEND_DIR/frontend.log"
        print_info "   进程 PID: $FRONTEND_PID"
    else
        print_error "前端服务启动失败"
    fi
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
    
    # 停止前端
    kill_port $FRONTEND_PORT
    
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
    
    echo ""
    
    # 检查前端
    if ! check_port $FRONTEND_PORT; then
        print_success "前端服务: 运行中 ✓"
        print_info "   http://localhost:$FRONTEND_PORT"
    else
        print_warning "前端服务: 未运行（推荐直接访问后端首页）"
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
    echo "  ${GREEN}./start.sh all${NC}     - 启动前后端服务"
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
    echo "  - 前端端口: $FRONTEND_PORT"
    echo ""
    echo "${BOLD}文件位置:${NC}"
    echo "  - 后端代码: $BACKEND_DIR/main_slim_v2.py"
    echo "  - 前端代码: $FRONTEND_DIR/index.html"
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
            start_frontend
            echo ""
            print_success "🎉 所有服务启动完成！"
            echo ""
            print_info "访问地址:"
            echo "  🌐 前端看板: http://localhost:$FRONTEND_PORT"
            echo "  🔌 API 服务: http://localhost:$API_PORT"
            echo "  📚 API 文档: http://localhost:$API_PORT/docs"
            echo ""
            
            # 自动打开浏览器（macOS）
            if [[ "$OSTYPE" == "darwin"* ]]; then
                print_info "正在打开浏览器..."
                sleep 2
                open "http://localhost:$FRONTEND_PORT"
            fi
            
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
