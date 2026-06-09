#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
from curl_cffi import requests
from bs4 import BeautifulSoup

# ==================== 配置区 ====================

# 代理配置（Xray 本地 SOCKS5 端口）
PROXY_SERVER = "socks5://127.0.0.1:1080"
PROXIES = {
    "http": PROXY_SERVER,
    "https": PROXY_SERVER
}

# Zampto 配置（从环境变量读取）
ZAMPTO_USERNAME = os.getenv("ZAMPTO_USERNAME")
ZAMPTO_PASSWORD = os.getenv("ZAMPTO_PASSWORD")
ZAMPTO_SERVER_ID = os.getenv("ZAMPTO_SERVER_ID")

# WxPusher 配置（从环境变量读取，可选）
WXPUSHER_TOKEN = os.getenv("WXPUSHER_TOKEN")
WXPUSHER_UID = os.getenv("WXPUSHER_UID")

# Zampto 基础 URL
BASE_URL = "https://zampto.com"

# ==================== 工具函数 ====================

def send_wxpusher(title, content):
    """发送 WxPusher 通知"""
    if not WXPUSHER_TOKEN or not WXPUSHER_UID:
        print("WxPusher 未配置，跳过通知")
        return
    
    url = "http://wxpusher.zjiecode.com/api/send/message"
    data = {
        "appToken": WXPUSHER_TOKEN,
        "content": content,
        "summary": title,
        "contentType": 1,
        "uids": [WXPUSHER_UID]
    }
    
    try:
        # 通知接口通常不需要强指纹，使用普通 requests 即可，若失败可忽略
        import requests as std_requests
        resp = std_requests.post(url, json=data, timeout=10)
        if resp.status_code == 200:
            result = resp.json()
            if result.get("code") == 1000:
                print(f"✅ WxPusher 通知发送成功: {title}")
            else:
                print(f"❌ WxPusher 通知失败: {result.get('msg')}")
    except Exception as e:
        print(f"❌ WxPusher 异常: {e}")


def check_proxy():
    """检查代理是否正常工作"""
    try:
        # 使用 curl_cffi 模拟浏览器检查代理
        resp = requests.get("https://ifconfig.me", proxies=PROXIES, timeout=10, impersonate="chrome124")
        ip = resp.text.strip()
        print(f"✅ 代理正常，出口 IP: {ip}")
        return True
    except Exception as e:
        print(f"❌ 代理检查失败: {e}")
        return False


# ==================== 核心功能 ====================

def login(session):
    """登录 Zampto"""
    print(f"🔐 正在登录: {ZAMPTO_USERNAME}")
    
    # 💡 核心技巧：先访问一次首页，让 WAF 下发正常的初始 Cookie，大幅降低被拦截概率
    try:
        session.get(f"{BASE_URL}/", proxies=PROXIES, timeout=30)
    except Exception:
        pass # 忽略首页访问错误，继续尝试登录页
    
    login_url = f"{BASE_URL}/login"
    try:
        resp = session.get(login_url, proxies=PROXIES, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"❌ 访问登录页面失败: {e}")
        return False
    
    # 解析 CSRF token
    soup = BeautifulSoup(resp.text, 'html.parser')
    csrf_input = soup.find('input', {'name': '_token'})
    
    if not csrf_input:
        print("❌ 未找到 CSRF token")
        print(f"⚠️ HTTP 状态码: {resp.status_code}")
        print(f"⚠️ 页面内容片段 (前 500 字符): \n{resp.text[:500].strip()}")
        
        if "cloudflare" in resp.text.lower() or "redirecting" in resp.text.lower():
            print("⚠️ 依然被 WAF 拦截。请确认 Zampto 的登录路径是否为 /login，或尝试更换代理节点。")
        return False
    
    csrf_token = csrf_input.get('value')
    
    # 提交登录
    login_data = {
        '_token': csrf_token,
        'email': ZAMPTO_USERNAME,
        'password': ZAMPTO_PASSWORD
    }
    
    try:
        resp = session.post(login_url, data=login_data, proxies=PROXIES, timeout=30, allow_redirects=False)
        
        if resp.status_code in [301, 302]:
            print("✅ 登录成功")
            return True
        else:
            print(f"❌ 登录失败: HTTP {resp.status_code}")
            print(f"⚠️ 响应片段: {resp.text[:200]}")
            return False
    except Exception as e:
        print(f"❌ 登录请求异常: {e}")
        return False


def get_servers(session):
    """获取服务器列表"""
    print("📡 正在获取服务器列表...")
    
    servers_url = f"{BASE_URL}/servers"
    try:
        resp = session.get(servers_url, proxies=PROXIES, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"❌ 获取服务器列表失败: {e}")
        return []
    
    soup = BeautifulSoup(resp.text, 'html.parser')
    server_rows = soup.find_all('tr')
    
    servers = []
    for row in server_rows:
        cells = row.find_all('td')
        if len(cells) >= 2:
            server_id = cells[0].get_text(strip=True)
            server_name = cells[1].get_text(strip=True)
            servers.append({
                'id': server_id,
                'name': server_name
            })
    
    print(f"✅ 找到 {len(servers)} 个服务器")
    return servers


def start_server(session, server_id):
    """启动指定服务器"""
    print(f"🚀 正在启动服务器: {server_id}")
    
    start_url = f"{BASE_URL}/server/{server_id}/start"
    
    try:
        resp = session.get(f"{BASE_URL}/server/{server_id}", proxies=PROXIES, timeout=30)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        csrf_input = soup.find('input', {'name': '_token'})
        if not csrf_input:
            print("❌ 未找到 CSRF token (启动页面)")
            return False
        
        csrf_token = csrf_input.get('value')
        
        resp = session.post(start_url, data={'_token': csrf_token}, proxies=PROXIES, timeout=60)
        
        if resp.status_code == 200:
            print(f"✅ 服务器 {server_id} 启动成功")
            return True
        else:
            print(f"❌ 服务器启动失败: HTTP {resp.status_code}")
            return False
    except Exception as e:
        print(f"❌ 启动服务器异常: {e}")
        return False


def stop_server(session, server_id):
    """停止指定服务器"""
    print(f"🛑 正在停止服务器: {server_id}")
    
    stop_url = f"{BASE_URL}/server/{server_id}/stop"
    
    try:
        resp = session.get(stop_url, proxies=PROXIES, timeout=30)
        if resp.status_code == 200:
            print(f"✅ 服务器 {server_id} 已停止")
            return True
        else:
            print(f"❌ 停止服务器失败: HTTP {resp.status_code}")
            return False
    except Exception as e:
        print(f"❌ 停止服务器异常: {e}")
        return False


def restart_server(session, server_id):
    """重启服务器"""
    print(f"🔄 正在重启服务器: {server_id}")
    stop_server(session, server_id)
    time.sleep(5)
    return start_server(session, server_id)


# ==================== 主程序 ====================

def main():
    print("=" * 50)
    print("🎮 Zampto Auto Script")
    print("=" * 50)
    
    if not ZAMPTO_USERNAME or not ZAMPTO_PASSWORD:
        print("❌ 缺少 Zampto 账号配置")
        sys.exit(1)
    
    if not check_proxy():
        send_wxpusher("❌ Zampto 代理失败", "代理检查失败，请检查 V2RAY_CONFIG 配置")
        sys.exit(1)
    
    # 💡 核心修改：创建 Session 时指定 impersonate="chrome124"，完美模拟真实浏览器指纹
    session = requests.Session(impersonate="chrome124")
    
    if not login(session):
        send_wxpusher("❌ Zampto 登录失败", f"账号: {ZAMPTO_USERNAME}\n请查看日志排查 WAF 拦截原因。")
        sys.exit(1)
    
    start_only = "--start-only" in sys.argv
    
    if start_only:
        if not ZAMPTO_SERVER_ID:
            print("❌ 缺少 ZAMPTO_SERVER_ID 配置")
            sys.exit(1)
        
        success = start_server(session, ZAMPTO_SERVER_ID)
        if success:
            send_wxpusher("✅ Zampto 服务器已启动", f"服务器 ID: {ZAMPTO_SERVER_ID}")
        else:
            send_wxpusher("❌ Zampto 启动失败", f"服务器 ID: {ZAMPTO_SERVER_ID}")
    else:
        servers = get_servers(session)
        
        if not servers:
            print("⚠️ 未找到服务器，尝试启动指定服务器")
            if ZAMPTO_SERVER_ID:
                success = restart_server(session, ZAMPTO_SERVER_ID)
                if success:
                    send_wxpusher("✅ Zampto 服务器已重启", f"服务器 ID: {ZAMPTO_SERVER_ID}")
                else:
                    send_wxpusher("❌ Zampto 重启失败", f"服务器 ID: {ZAMPTO_SERVER_ID}")
            else:
                send_wxpusher("⚠️ Zampto 无服务器", "未找到任何服务器")
        else:
            success_count = 0
            for server in servers:
                if restart_server(session, server['id']):
                    success_count += 1
                time.sleep(3)
            
            msg = f"成功重启 {success_count}/{len(servers)} 个服务器"
            send_wxpusher("✅ Zampto 自动重启完成", msg)
    
    print("=" * 50)
    print("✅ 任务完成")
    print("=" * 50)


if __name__ == "__main__":
    main()
