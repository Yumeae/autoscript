import time
import json
import os
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# ==============================================================================
# --- 1. 配置区域 ---
# ==============================================================================

# 日常模式 URL
NORMAL_LIST_URL = 'https://i.jielong.com/c/2XVVRCM9S9'
EXCLUSION_LIST_URL = 'https://i.jielong.com/c/2XVJ9YRCS7'

# 全体应到人员名单
ALL_MEMBERS = {
    "马志远", "窦丽雯", "吴东澔", "辛琦", "李小美", "彭海雨", "方培宇",
    "韩朝旭", "段智煜", "黄俊泽", "班梓超", "王瑶", "汤钊宇", "殷广昱",
    "齐伯岩", "丁梓彧", "赵子豪", "陈宇晗", "贾天睿", "闫浩男", "孟隽羽",
    "李甜", "赵淑雅", "周亦乔", "杨常露", "郑国伟", "林纪宁"
}

# --- QMSG 配置 (从 GitHub Actions Secrets 读取) ---
QMSG_KEY = os.getenv('QMSG_KEY')
qmsg_target_json = os.getenv('QMSG_TARGET_QQS_JSON')
QMSG_TARGET_QQS = json.loads(qmsg_target_json) if qmsg_target_json else []

# 启动前检查 Secrets 是否成功加载
if not QMSG_KEY or not QMSG_TARGET_QQS:
    print("[严重错误] 无法从环境变量加载 QMSG_KEY 或 QMSG_TARGET_QQS_JSON。请检查 GitHub Secrets 配置。")
    exit(1)

# ==============================================================================
# --- 2. Selenium 核心功能 ---
# ==============================================================================

def setup_driver():
    """配置并返回一个 Selenium WebDriver 实例"""
    options = webdriver.ChromeOptions()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    try:
        service = webdriver.ChromeService()
        driver = webdriver.Chrome(service=service, options=options)
        return driver
    except Exception as e:
        print(f"[严重错误] WebDriver 初始化失败！: {e}")
        return None

def scrape_names_with_selenium(driver, url, selector, description):
    """通用爬虫函数，根据URL和CSS选择器爬取名字"""
    try:
        print(f"--- 开始爬取 '{description}' ---")
        driver.get(url)
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".name-list")))
        print("动态内容加载完成，开始解析...")
        time.sleep(1)
        name_elements = driver.find_elements(By.CSS_SELECTOR, selector)
        scraped_members = {elem.text for elem in name_elements if elem.text.strip()}
        print(f"解析完成，找到 {len(scraped_members)} 个名字。")
        return scraped_members
    except TimeoutException:
        print(f"解析超时或页面无报名信息 ({description})。")
        return set()
    except Exception as e:
        print(f"[错误] Selenium 爬取时发生未知错误 ({description}): {e}")
        return None

# ==============================================================================
# --- 3. Qmsg酱 对接功能 ---
# ==============================================================================
def send_to_qmsg(key, target_qq, title, message):
    api_url = f"https://qmsg.zendee.cn/send/{key}"
    cleaned_message = message.replace('**', '').replace('## ℹ️ ', '').replace('## ❌ ', '').replace('## ', '').replace('> ', '').replace('\n\n---\n\n', '\n')
    full_message = f"{title}\n--------------------\n{cleaned_message}"
    payload = {'qq': target_qq, 'msg': full_message}
    try:
        print(f"--- 正在发送 Qmsg酱 通知到 {target_qq}... ---")
        response = requests.post(api_url, data=payload, timeout=10)
        response.raise_for_status()
        result = response.json()
        if result.get('success'):
            print(f"Qmsg酱 通知发送到 {target_qq} 成功！")
        else:
            reason = result.get('reason', '未知错误')
            print(f"[错误] Qmsg酱 通知发送到 {target_qq} 失败: {reason}")
    except Exception as e:
        print(f"[错误] 发送 Qmsg酱 通知时发生错误: {e}")

# ==============================================================================
# --- 4. 主逻辑执行区域 ---
# ==============================================================================
if __name__ == "__main__":
    print("--- 开始执行自动考勤统计脚本 ---")
    driver = setup_driver()
    if driver is None:
        print("--- 脚本因WebDriver错误而提前终止 ---")
        exit(1)
    
    try:
        normal_selector = 'div.name-list:not(.name-active) .name'
        normal_absent_list = scrape_names_with_selenium(driver, NORMAL_LIST_URL, normal_selector, "日常缺席名单")
        exclusion_selector = 'div.name-active.name-list .name'
        approved_absent_list = scrape_names_with_selenium(driver, EXCLUSION_LIST_URL, exclusion_selector, "特批缺席名单")

        if normal_absent_list is None or approved_absent_list is None:
            raise Exception("爬取缺席名单时失败")

        final_absent_list = normal_absent_list - approved_absent_list

        if not final_absent_list and not approved_absent_list:
            title = "晚点名：全员已到齐"
            message = (f"**网安2401班今日{len(ALL_MEMBERS)}人在校**\n\n")
        else:
            total_absent_count = len(final_absent_list) + len(approved_absent_list)
            present_count = len(ALL_MEMBERS) - total_absent_count
            title = f"晚点名：{total_absent_count} 人情况汇总"
            status_line = f"网安2401班今日{present_count}人在校"
            report_parts = []
            if final_absent_list:
                report_parts.append(f"{'、'.join(sorted(list(final_absent_list)))} 未打卡")
            if approved_absent_list:
                report_parts.append(f"{'、'.join(sorted(list(approved_absent_list)))} 不在校")
            report_body = "，".join(report_parts)
            message = (f"**{status_line}**，{report_body}\n\n")

        print(f"\n--- 开始批量发送通知给 {len(QMSG_TARGET_QQS)} 个用户 ---")
        for target_qq in QMSG_TARGET_QQS:
            send_to_qmsg(QMSG_KEY, target_qq, title, message)
            time.sleep(1)
    except Exception as e:
        print(f"\n[严重错误] 脚本在主逻辑执行期间发生异常: {e}")
        title = "考勤脚本执行异常"
        message = (f"## ❌ 脚本执行异常\n\n**错误详情**: `{e}`\n")
        for target_qq in QMSG_TARGET_QQS:
            send_to_qmsg(QMSG_KEY, target_qq, title, message)
            time.sleep(1)
    finally:
        print("\n--- 关闭浏览器... ---")
        driver.quit()
        print("--- 脚本执行完毕 ---")