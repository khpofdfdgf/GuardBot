"""
web/terminal.py
Router Web API (FastAPI) - Chuyển hẳn sang HTTP thuần bằng ShellInABox
Tích hợp Xác thực Credential Động từ Discord (Hạn dùng 1 ngày)
Bypass hoàn toàn lỗi UnicodeEncodeError trên HTTP Headers.
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, JSONResponse
import subprocess
import random
import time
import socket
import httpx
import os
import base64
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/terminal", tags=["Terminal Control"])

BASE_PORT = 6200
current_port = BASE_PORT

def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def find_available_port(start_port: int) -> int:
    port = start_port
    while is_port_in_use(port):
        port += 1
        if port > start_port + 50:
            break
    return port

def check_admin_permission(request: Request):
    uid = request.session.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập hệ thống.")
        
    user_data = request.app.state.user_store.get(uid)
    if not user_data:
        raise HTTPException(status_code=401, detail="Phiên đăng nhập không hợp lệ.")
        
    is_admin = any(
        g.get("owner") or (int(g.get("permissions", 0)) & 0x20)
        for g in (user_data.get("guilds", []) if isinstance(user_data.get("guilds"), list) else [])
    )
    
    if not is_admin:
        raise HTTPException(status_code=403, detail="Cảnh báo: Bạn không có quyền truy cập Terminal!")

def verify_terminal_credential(request: Request):
    """Kiểm tra thời gian hiệu lực 1 ngày của Credential"""
    session = getattr(request.app.state, "terminal_session", None)
    if not session:
        raise HTTPException(status_code=401, detail="Chưa khởi tạo phiên làm việc hoặc phiên đã bị hủy.")
        
    if datetime.utcnow() > session.get("expire_at"):
        request.app.state.terminal_session = None
        subprocess.run("pkill -9 -f shellinaboxd", shell=True)
        raise HTTPException(status_code=401, detail="Thông tin xác thực đã hết hạn sử dụng (Quá 1 ngày). Vui lòng tạo phiên mới.")

@router.post("/start")
async def start_terminal(request: Request):
    check_admin_permission(request)
    global current_port
    
    subprocess.run("pkill -9 -f shellinaboxd", shell=True)
    time.sleep(0.4)
    
    current_port = find_available_port(BASE_PORT)
    
    secret_user = f"admin_{random.randint(10, 99)}"
    secret_pass = f"guard_{random.randint(100000, 999999)}"
    expire_time = datetime.utcnow() + timedelta(days=1)
    
    request.app.state.terminal_session = {
        "username": secret_user,
        "password": secret_pass,
        "port": current_port,
        "expire_at": expire_time
    }
    
    try:
        username = subprocess.check_output("id -un", shell=True).decode().strip()
        groupname = subprocess.check_output("id -gn", shell=True).decode().strip()
        user_home = os.path.expanduser(f"~{username}")
    except Exception:
        username = "root"
        groupname = "root"
        user_home = "/root"

    shell_cmd = (
        f"shellinaboxd -p {current_port} --localhost-only -t --background --disable-peer-check "
        f"--user-css 'Normal:+/dev/null' "
        f"-s '/:{username}:{groupname}:{user_home}:tmux attach -t guardbot'"
    )
    
    log_file = open("data/shellinabox.log", "w")
    
    try:
        subprocess.Popen(
            f"tmux kill-session -t guardbot 2>/dev/null; tmux new-session -d -s guardbot bash; {shell_cmd}",
            shell=True, stdout=log_file, stderr=log_file
        )
        
        is_ready = False
        for _ in range(30):
            if is_port_in_use(current_port):
                is_ready = True
                break
            time.sleep(0.1)
        log_file.close()

        if not is_ready:
            request.app.state.terminal_session = None
            raise HTTPException(status_code=500, detail="Cổng dịch vụ ShellInABox không thể khởi động.")

        return {
            "status": "online",
            "url": "/api/terminal/stream",
            "username": secret_user,   
            "password": secret_pass,   
            "expire_at": expire_time.isoformat()
        }
    except Exception as e:
        if not log_file.closed: log_file.close()
        request.app.state.terminal_session = None
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stop")
async def stop_terminal(request: Request):
    check_admin_permission(request)
    subprocess.run("pkill -9 -f shellinaboxd", shell=True)
    request.app.state.terminal_session = None
    return {"status": "offline", "message": "Da tat Terminal va huy hoan toan Credential cu."}

# ─── REVERSE HTTP PROXY FIX LỖI POPUP & ĐEN MÀN HÌNH ──────────────────────

@router.get("/stream")
@router.get("/stream/{path:path}")
async def terminal_http_proxy(request: Request, path: str = ""):
    check_admin_permission(request)
    verify_terminal_credential(request)
    
    global current_port
    session = request.app.state.terminal_session
    
    auth_header = request.headers.get("Authorization")
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    
    # Mẹo lấy Auth từ Cookie nếu Iframe load (Giúp Iframe hết bị đen màn hình)
    cookie_auth = request.cookies.get("terminal_auth")
    
    encoded_creds = None
    if auth_header and auth_header.startswith("Basic "):
        encoded_creds = auth_header.split(" ", 1)[1]
    elif cookie_auth:
        encoded_creds = cookie_auth

    # [Đoạn code kiểm tra cũ thay bằng đoạn này]
    if not encoded_creds:
        if is_ajax:
            return JSONResponse(status_code=401, content={"detail": "Chưa cung cấp thông tin xác thực."})
        else:
            # Bỏ WWW-Authenticate, trả về trang thông báo lỗi thuần túy cho Iframe
            return Response(status_code=401, content="<h3>Chua dang nhap Terminal! Vui long nhap credential tren giao dien web.</h3>", media_type="text/html")
        
    try:
        decoded_creds = base64.b64decode(encoded_creds).decode("utf-8")
        input_user, input_pass = decoded_creds.split(":", 1)
        
        if input_user != session["username"] or input_pass != session["password"]:
            if is_ajax:
                return JSONResponse(status_code=401, content={"detail": "Sai thông tin!"})
            else:
                return Response(status_code=401, content="<h3>Sai tai khoan hoac mat khau dong!</h3>", media_type="text/html")
    except Exception:
        if is_ajax:
            return JSONResponse(status_code=401, content={"detail": "Lỗi xác thực."})
        else:
            return Response(status_code=401, content="<h3>Loi dinh dang xac thuc!</h3>", media_type="text/html")

    # Tiến hành proxy forward dữ liệu sang ShellInABox khi thông tin ĐÚNG
    # ─── ĐOẠN PROXY FORWARD NẰM CUỐI HÀM GET /STREAM ───
    target_path = f"/{path}" if path else "/"
    url = f"http://127.0.0.1:{current_port}{target_path}"
    
    # Chuẩn hóa lại Header để ép thông tin xác thực chuẩn Basic Auth sang cho ShellInABox
    forward_headers = dict(request.headers)
    forward_headers["Authorization"] = f"Basic {encoded_creds}"
    
    async with httpx.AsyncClient(timeout=None) as client:
        params = dict(request.query_params)
        # Truyền forward_headers thay vì dict(request.headers) cũ
        proxy_res = await client.get(url, headers=forward_headers, params=params)
        return Response(
            content=proxy_res.content, 
            status_code=proxy_res.status_code, 
            media_type=proxy_res.headers.get("content-type", "text/html")
        )

@router.post("/stream/{path:path}")
async def terminal_http_post_proxy(request: Request, path: str = ""):
    check_admin_permission(request)
    verify_terminal_credential(request)
    global current_port
    
    target_path = f"/{path}" if path else "/"
    url = f"http://127.0.0.1:{current_port}{target_path}"
    body = await request.body()
    
    async with httpx.AsyncClient(timeout=None) as client:
        proxy_res = await client.post(url, headers=dict(request.headers), content=body)
        return Response(
            content=proxy_res.content, 
            status_code=proxy_res.status_code, 
            media_type=proxy_res.headers.get("content-type", "text/plain")
        )