# -*- coding: utf-8 -*-
# 导入所需的库
import requests
import json
import time
import os
import hmac
import hashlib
import base64
import urllib.parse
import re

# --- 1. 配置区域 ---

# 从环境变量（GitHub Secrets）中加载所有敏感信息
DINGTALK_WEBHOOK = os.environ.get('DINGTALK_WEBHOOK')
DINGTALK_SECKEY = os.environ.get('DINGTALK_SECKEY')
JSESSIONID = os.environ.get('JSESSIONID')

# 检查所有必需的密钥（Secrets）是否已成功加载
if not all([DINGTALK_WEBHOOK, DINGTALK_SECKEY, JSESSIONID]):
    print("❌ 错误：缺少一个或多个必要的环境变量（Secrets）。")
    print("请在GitHub仓库的 Secrets 设置中配置 DINGTALK_WEBHOOK, DINGTALK_SECKEY, 和 JSESSIONID。")
    exit(1) # 如果密钥不全，则退出脚本

# 重试逻辑配置
MAX_ATTEMPTS = 3  # 总尝试次数（首次尝试 + 2次重试）
RETRY_DELAY_SECONDS = 5  # 每次重试间的等待秒数
RETRY_ERROR_MESSAGE = "抱歉由于网络或设备问题，暂时无法获得电表电量及状态信息,请稍后再试!"

# 请求体配置（通常无需修改）
QUERY_PAYLOAD = {
    "query_elec_roominfo": {
        "aid": "0030000000006001", "account": "26577",
        "room": {"roomid": "20161009111811624619", "room": "1栋609"},
        "floor": {"floorid": "6", "floor": "6层"},
        "area": {"area": "天津工业大学", "areaname": "天津工业大学"},
        "building": {"buildingid": "20161008184448464922", "building": "西苑7号楼"}
    }
}
# --- 配置区域结束 ---


def get_electricity_info():
    """
    发送请求以获取电费信息，并包含完整的重试逻辑。
    函数将返回一个元组：(结果字典, 错误信息字符串)。成功时错误为None，失败时结果为None。
    """
    url = "http://wxjdf.tiangong.edu.cn:9910/web/Common/Tsm.html"
    headers = {
        'Host': 'wxjdf.tiangong.edu.cn:9910', 'Connection': 'keep-alive',
        'Accept': 'application/json, text/javascript, */*; q=0.01', 'X-Requested-With': 'XMLHttpRequest',
        'User-Agent': 'Mozilla/5.0 (Linux; Android 12; SM-F926U Build/V417IR; wv) AppleWebKit/5.36 (KHTML, like Gecko) Version/4.0 Chrome/101.0.4951.61 Safari/5.36 MMWEBID/2279 MicroMessenger/8.0.58.2841(0x28003A35) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64',
        'Content-Type': 'application/x-form-urlencoded; charset=UTF-8',
        'Origin': 'http://wxjdf.tiangong.edu.cn:9910',
        'Referer': 'http://wxjdf.tiangong.edu.cn:9910/web/common/checkEle.html?ticket=ff9d7ff75466e04703b7717db92827d7&visitor=0&appId=33&synAccessSource=wechat-work&loginFrom=wechat-work&type=app',
        'Accept-Encoding': 'gzip, deflate', 'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
        'Cookie': f'JSESSIONID={JSESSIONID}', 'Proxy-Connection': 'Close',
    }
    jsondata_string = json.dumps(QUERY_PAYLOAD, separators=(',', ':'))
    payload = {
        'jsondata': jsondata_string, 'funname': 'synjones.onecard.query.elec.roominfo', 'json': 'true'
    }

    # 循环尝试发送请求
    for attempt in range(MAX_ATTEMPTS):
        print(f"🚀 第 {attempt + 1} / {MAX_ATTEMPTS} 次尝试: 正在发送请求...")
        try:
            response = requests.post(url, headers=headers, data=payload, timeout=15)
            if response.status_code != 200:
                return None, f"请求失败：服务器返回了错误的状态码 {response.status_code}。"
            
            response_data = response.json()
            errmsg = response_data.get("query_elec_roominfo", {}).get("errmsg", "")

            if errmsg == RETRY_ERROR_MESSAGE:
                print(f"⚠️ 收到了需要重试的特定错误信息: '{errmsg}'")
                if attempt < MAX_ATTEMPTS - 1:
                    print(f"   将在 {RETRY_DELAY_SECONDS} 秒后重试...")
                    time.sleep(RETRY_DELAY_SECONDS)
                    continue
                else:
                    return None, f"已达到最大尝试次数（{MAX_ATTEMPTS}次）。最后一次错误: {errmsg}"
            
            success_match = re.search(r'剩余购电量:(\d+\.?\d*)度', errmsg)
            if success_match:
                result = {
                    "room_info": f"{QUERY_PAYLOAD['query_elec_roominfo']['building']['building']} {QUERY_PAYLOAD['query_elec_roominfo']['room']['room']}",
                    "remaining_kwh": success_match.group(1)
                }
                return result, None
            else:
                return None, f"查询失败，收到未知的服务器消息: {errmsg}"

        except json.JSONDecodeError:
            error_preview = response.text[:300].strip() if response and response.text else "无法获取响应内容"
            return None, f"服务器响应格式错误（不是JSON）。这很可能是因为`JSESSIONID`过期了。\n\n**服务器响应预览**:\n```\n{error_preview}\n```"
        except requests.exceptions.RequestException as e:
            return None, f"网络请求异常: {e}"
    
    return None, f"经过 {MAX_ATTEMPTS} 次尝试后，查询依然失败。"


def send_to_dingtalk(title, text):
    """发送Markdown格式的消息到钉钉机器人（带安全加签）"""
    print(f"🤖 正在准备发送钉钉通知: '{title}'")
    timestamp = str(round(time.time() * 1000))
    secret_enc = DINGTALK_SECKEY.encode('utf-8')
    string_to_sign = f'{timestamp}\n{DINGTALK_SECKEY}'
    hmac_code = hmac.new(secret_enc, string_to_sign.encode('utf-8'), digestmod=hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    
    signed_url = f"{DINGTALK_WEBHOOK}&timestamp={timestamp}&sign={sign}"
    payload = {"msgtype": "markdown", "markdown": {"title": title, "text": text}}
    
    try:
        response = requests.post(signed_url, headers={'Content-Type': 'application/json'}, data=json.dumps(payload), timeout=10)
        if response.json().get("errcode") == 0:
            print("✅ 钉钉消息发送成功！")
        else:
            print(f"❌ 钉钉消息发送失败: {response.json().get('errmsg')}")
    except Exception as e:
        print(f"❌ 发送钉钉消息时出现异常: {e}")

# --- 主程序入口 ---
if __name__ == "__main__":
    result, error = get_electricity_info()
    current_time = time.strftime('%Y-%m-%d %H:%M:%S')

    if result:
        # --- 常规成功消息 ---
        title = "电费小报告来啦！"
        message = (
            f"### ☀️ {title}\n\n"
            f"亲爱的小伙伴，截至当前，寝室 **{result['room_info']}** 的电费情况如下：\n\n"
            f"## **剩余电量**: <font color='#228B22' size=5>{result['remaining_kwh']}</font> 度\n\n"
            f"> 💡 电量充足，请放心使用！又是元气满满的一天哦 💪\n\n"
            f"***\n"
            f"<font color='#808080' size=2>报告时间: {current_time}</font>"
        )
        print(f"✅ 查询成功: {result['room_info']}, 剩余电量: {result['remaining_kwh']} 度")
        send_to_dingtalk(title, message)

        # --- ⭐ 新增：低电量预警判断 ---
        try:
            remaining_float = float(result['remaining_kwh'])
            if remaining_float < 10:
                # 如果电量低于10度，构造并发送第二条预警消息
                alert_title = "⚠️ 注意！电量快要用完啦！"
                alert_message = (
                    f"### 🚨 {alert_title}\n\n"
                    f"**紧急提醒**：寝室 **{result['room_info']}** 的电量即将耗尽！\n\n"
                    f"## **剩余电量**: <font color='#FF0000' size=5>{result['remaining_kwh']}</font> 度\n\n"
                    f"> 😱 **非常危险！** 为了避免突然断电的尴尬，请尽快安排充电哦！\n\n"
                    f"***\n"
                    f"<font color='#808080' size=2>预警时间: {current_time}</font>"
                )
                print(f"发出低电量预警: {remaining_float} 度 < 10 度")
                # 稍微延迟一下，避免两条消息发送太快
                time.sleep(1)
                send_to_dingtalk(alert_title, alert_message)
        except ValueError:
            print("❌ 解析剩余电量为数字时失败，无法进行低电量判断。")

    else:
        # --- 失败消息 ---
        title = "哎呀，查询失败了"
        message = (
            f"### 🚨 {title}\n\n"
            f"电小璃努力尝试了好几次，但没能成功获取到电费信息。\n\n"
            f"**失败详情**:\n"
            f"> {error}\n\n"
            f"**我猜可能是**:\n"
            f"> 1. **`JSESSIONID` 过期了** (最常见！)，需要去GitHub Secrets里更新一下哦。\n"
            f"> 2. 学校的查询服务器暂时“打了个盹”，可以稍后看看会不会自动恢复。\n\n"
            f"***\n"
            f"<font color='#808080' size=2>报告时间: {current_time}</font>"
        )
        print(f"❌ 查询失败: {error}")
        send_to_dingtalk(title, message)
