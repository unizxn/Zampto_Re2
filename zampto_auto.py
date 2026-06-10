#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import requests
from requests.cookies import RequestsCookieJar
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
# 【修改点】：使用最新的 stealth API
from playwright_stealth import stealth

# ==================== 配置区 ====================

PROXY_SERVER = "socks5://127.0.0.1:1080"
PROXIES = {
    "http": PROXY_SERVER,
    "https": PROXY_SERVER
}

ZAMPTO_USERNAME = os.getenv("ZAMPTO_USERNAME")
ZAMPTO_PASSWORD = os.getenv("ZAMPTO_PASSWORD")
ZAMPTO_SERVER_ID = os.getenv("ZAMPTO_SERVER_ID")

WXPUSHER_TOKEN = os.getenv("WXPUSHER_TOKEN")
WXPUSHER_UID = os.getenv("WXPUSHER_UID")

BASE_URL = "https://zampto.com"

# ==================== 工具函数 ====================

def send_wxpusher(title, content):
    if not WXPUSHER_TOKEN or not WXPUSHER_UID:
        return
    url = "http://wxpusher.zjiecode.com/api/send/message"
    data = {
        "appToken": WXPUSHER_TOKEN, "content": content, "summary": title,
        "contentType": 1, "uids": [WXPUSHER_UID]
    }
    try:
        requests.post(url, json=data, timeout=10)
    except Exception:
        pass

def check_proxy():
    try:
        resp = requests.get("https://ifconfig.me", proxies=PROXIES, timeout=10)
        print(f"✅ 代理正常，出口 IP: {resp.text.strip()}")
        return True
    except Exception as e:
        print(f"❌ 代理检查失败: {e}")
        return False

# ==================== 核心功能 ====================

def login_and_get_cookies():
    """使用 Playwright 模拟真实浏览器登录，绕过 Cloudflare 并提取 Cookie"""
    print(f"🔐 正在启动 Playwright 浏览器并绕过 Cloudflare...")
    
    try:
        with sync_playwright() as p:
            # 启动 Chromium，配置 SOCKS5 代理
            browser = p.chromium.launch(
                headless=True,
                proxy={"server": PROXY_SERVER}
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080}
            )
            page = context.new_page()
            
            # 【修改点】：应用 stealth 补丁，隐藏自动化特征
            stealth(page)

            # 访问登录页
            page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded")
            
            # 等待 Cloudflare 挑战完成，出现登录表单的 email 输入框 (最多等 20 秒)
            try:
                page.wait_for_selector('input[name="email"]', timeout=20000)
                print("✅ Cloudflare 验证通过，找到登录表单")
            except Exception:
                print(f"❌ 等待登录表单超时，可能被 CF 拦截。当前页面标题: {page.title()}")
                browser.close()
                return None

            # 填写账号密码
            page.fill('input[name="email"]', ZAMPTO_USERNAME)
            page.fill('input[name="password"]', ZAMPTO_PASSWORD)
            
            # 提交登录 (点击提交按钮或按回车)
            submit_clicked = False
            for selector in ['button[type="submit"]', 'input[type="submit"]', 'button:has-text("Login")', 'button:has-text("登录")']:
                try:
                    page.click(selector, timeout=2000)
                    submit_clicked = True
                    break
                except Exception:
                    continue
            
            if not submit_clicked:
                page.keyboard.press('Enter')

            # 等待登录成功后的页面加载
            page.wait_for_load_state("networkidle", timeout=15000)
            
            # 检查是否登录成功（通过判断是否还在登录页）
            if "login" in page.url.lower():
                print("❌ 登录失败，账号或密码错误，或仍停留在登录页")
                browser.close()
                return None

            # 提取所有 Cookie
            cookies = context.cookies()
            browser.close()
            
            # 将 Playwright 的 Cookie 转换为 requests 可用的 CookieJar
            cookie_jar = RequestsCookieJar()
            for cookie in cookies:
                cookie_jar.set(cookie['name'], cookie['value'], domain=cookie.get('domain', ''), path=cookie.get('path', '/'))
                
            print("✅ 登录成功并提取 Cookie")
            return cookie_jar

    except Exception as e:
        print(f"❌ Playwright 运行异常: {e}")
        return None


def get_servers(session):
    print("📡 正在获取服务器列表...")
    try:
        resp = session.get(f"{BASE_URL}/servers", proxies=PROXIES, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"❌ 获取服务器列表失败: {e}")
        return []
    
    soup = BeautifulSoup(resp.text, 'html.parser')
    servers = []
    for row in soup.find_all('tr'):
        cells = row.find_all('td')
        if len(cells) >= 2:
            servers.append({'id': cells[0].get_text(strip=True), 'name': cells[1].get_text(strip=True)})
    
    print(f"✅ 找到 {len(servers)} 个服务器")
    return servers


def start_server(session, server_id):
    print(f"🚀 正在启动服务器: {server_id}")
    try:
        # 获取启动页面的 CSRF token
        resp = session.get(f"{BASE_URL}/server/{server_id}", proxies=PROXIES, timeout=30)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        csrf_input = soup.find('input', {'name': '_token'})
        if not csrf_input:
            print("❌ 未找到 CSRF token (可能未登录或页面结构变更)")
            return False
        
        # 提交启动请求
        resp = session.post(
            f"{BASE_URL}/server/{server_id}/start", 
            data={'_token': csrf_input.get('value')}, 
            proxies=PROXIES, 
            timeout=60
        )
        
        if resp.status_code == 200:
            print(f"✅ 服务器 {server_id} 启动成功")
            return True
        else:
            print(f" 服务器启动失败: HTTP {resp.status_code}")
            return False
    except Exception as e:
        print(f"❌ 启动服务器异常: {e}")
        return False


def stop_server(session, server_id):
    print(f"🛑 正在停止服务器: {server_id}")
    try:
        resp = session.get(f"{BASE_URL}/server/{server_id}/stop", proxies=PROXIES, timeout=30)
        if resp.status_code == 200:
            print(f"✅ 服务器 {server_id} 已停止")
            return True
    except Exception as e:
        print(f"❌ 停止服务器异常: {e}")
    return False


def restart_server(session, server_id):
    print(f" 正在重启服务器: {server_id}")
    stop_server(session, server_id)
    time.sleep(5)
    return start_server(session, server_id)


# ==================== 主程序 ====================

def main():
    print("=" * 50)
    print("🎮 Zampto Auto Script (Playwright 版)")
    print("=" * 50)
    
    if not ZAMPTO_USERNAME or not ZAMPTO_PASSWORD:
        print(" 缺少 Zampto 账号配置")
        sys.exit(1)
    
    if not check_proxy():
        send_wxpusher(" Zampto 代理失败", "代理检查失败")
        sys.exit(1)
    
    # 1. 使用 Playwright 登录并获取 Cookie
    cookie_jar = login_and_get_cookies()
    if not cookie_jar:
        send_wxpusher("❌ Zampto 登录失败", f"账号: {ZAMPTO_USERNAME}\n请检查日志排查 Cloudflare 拦截原因。")
        sys.exit(1)
    
    # 2. 创建 requests session 并注入 Cookie
    session = requests.Session()
    session.cookies.update(cookie_jar)
    
    # 3. 执行后续操作
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
            send_wxpusher("✅ Zampto 自动重启完成", f"成功重启 {success_count}/{len(servers)} 个服务器")
    
    print("=" * 50)
    print("✅ 任务完成")
    print("=" * 50)

if __name__ == "__main__":
    main()
