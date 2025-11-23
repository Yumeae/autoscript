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

# --- 1. 配置区域---

# 从环境变量（GitHub Secrets）中加载所有敏感信息
DINGTALK_WEBHOOK = os.environ.get('DINGTALK_WEBHOOK')
DINGTALK_SECKEY = os.environ.get('DINGTALK_SECKEY')
JSESSIONID = os.environ.get('JSESSIONID')

# 检查所有必需的密钥（Secrets）是否已成功加载
if not all([DINGTALK_WEBHOOK, DINGTALK_SECKEY, JSESSIONID]):
    print("❌ 错误：缺少一个或多个必要的环境变量（Secrets）。")
    print("请在GitHub仓库的 Secrets 设置中配置 DINGTALK_WEBHOOK, DINGTALK_SECKEY, 和 JSESSIONID。")
    exit(1) # 如果密钥不全，则退出脚本

# --- ⭐ 新增：要查询的寝室列表 ---
# 在这里添加或修改你要查询的寝室信息。
# 每个寝室是一个字典，包含一个自定义的名字和从请求包里抓取的信息。
DORM_LIST = [
    {
        "dorm_name": "西苑7号楼 1栋609",  # 自定义一个名字，方便看
        "buildingid": "20161008184448464922",
        "building": "西苑7号楼",
        "floorid": "6",
        "floor": "6层",
        "roomid": "20161009111811624619",
        "room": "1栋609"
    },
    {
        "dorm_name": "西苑3号楼 1栋430", # 这是你新提供的寝室
        "buildingid": "20161008182912026394",
        "building": "西苑3号楼",
        "floorid": "4",
        "floor": "4层",
        "roomid": "20161008225841597249",
        "room": "1栋430"
    }
    # 如果需要查询更多寝室，在这里继续添加
    # ,{
    #     "dorm_name": "...",
    #     "buildingid": "...",
    #     ...
    # }
]
# --- 配置区域结束 ---


def get_electricity_info(dorm_config):
    """
    使用“一丝不差”的终极模拟方式发送请求。
    函数现在接受一个寝室配置字典作为参数。
    """
    url = "http://wxjdf.tiangong.edu.cn:9910/web/Common/Tsm.html"
    headers = {
        'Host': 'wxjdf.tiangong.edu.cn:9910', 'Connection': 'keep-alive',
        'Accept': 'application/json, text/javascript, */*; q=0.01', 'X-Requested-With': 'XMLHttpRequest',
        'User-Agent': 'Mozilla/5.0 (Linux; Android 12; SM-F926U Build/V417IR; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/101.0.4951.61 Safari/537.36 MMWEBID/2279 MicroMessenger/8.0.58.2841(0x28003A52) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Origin': 'http://wxjdf.tiangong.edu.cn:9910',
        'Referer': 'http://wxjdf.tiangong.edu.cn:9910/web/common/checkEle.html?ticket=bebd82a45f10692a95317a8f4f3badf6&visitor=0&appId=33&synAccessSource=wechat-work&loginFrom=wechat-work&type=app',
        'Accept-Encoding': 'gzip, deflate', 'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
        'Cookie': f'JSESSIONID={JSESSIONID}', 'Proxy-Connection': 'Close',
    }

    # 动态构建请求体
    query_payload = {
      "query_elec_roominfo": {
        "aid": "0030000000006001", "account": "26577", # 这部分通常是固定的
        "room": {"roomid": dorm_config["roomid"], "room": dorm_config["room"]},
        "floor": {"floorid": dorm_config["floorid"], "floor": dorm_config["floor"]},
        "area": {"area": "天津工业大学", "areaname": "天津工业大学"},
        "building": {"buildingid": dorm_config["buildingid"], "building": dorm_config["building"]}
      }
    }
    jsondata_string = json.dumps(query_payload, separators=(',', ':'))
    payload = {
        'jsondata': jsondata_string, 'funname': 'synjones.onecard.query.elec.roominfo', 'json': 'true'
    }

    print(f"🚀 正在为寝室【{dorm_config['dorm_name']}】发送请求...")
    try:
        response = requests.post(url, headers=headers, data=payload, timeout=15)
        response_data = response.json()
        errmsg = response_data.get("query_elec_roominfo", {}).get("errmsg", "")
        success_match = re.search(r'剩余购电量:(\d+\.?\d*)度', errmsg)

        if success_match:
            result = {
                "dorm_name": dorm_config['dorm_name'],
                "remaining_kwh": success_match.group(1)
            }
            return result, None
        else:
            return None, f"查询失败，服务器消息: {errmsg}"

    except json.JSONDecodeError:
        return None, f"服务器响应格式错误（不是JSON）。响应预览:\n```\n{response.text[:300]}\n```"
    except requests.exceptions.RequestException as e:
        return None, f"网络请求异常: {e}"


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
    for dorm in DORM_LIST:
        print(f"\n{'='*10} 开始处理寝室: {dorm['dorm_name']} {'='*10}")
        result, error = get_electricity_info(dorm)
        current_time = time.strftime('%Y-%m-%d %H:%M:%S')

        if result:
            # --- 常规成功消息 ---
            title = f"电费报告 - {result['dorm_name']}"
            message = (
                f"### ☀️ 电费小报告来啦！\n\n"
                f"亲爱的小伙伴，截至当前，寝室 **{result['dorm_name']}** 的电费情况如下：\n\n"
                f"## **剩余电量**: <font color='#228B22' size=5>{result['remaining_kwh']}</font> 度\n\n"
                f"> 💡 电量充足，请放心使用！\n\n"
                f"***\n"
                f"<font color='#808080' size=2>报告时间: {current_time}</font>"
            )
            print(f"✅ 查询成功: {result['dorm_name']}, 剩余电量: {result['remaining_kwh']} 度")
            send_to_dingtalk(title, message)

            # --- 低电量预警判断 ---
            try:
                remaining_float = float(result['remaining_kwh'])
                if remaining_float < 10:
                    alert_title = f"⚠️ 电量预警 - {result['dorm_name']}"
                    alert_message = (
                        f"### 🚨 {alert_title}\n\n"
                        f"**紧急提醒**：寝室 **{result['dorm_name']}** 的电量即将耗尽！\n\n"
                        f"## **剩余电量**: <font color='#FF0000' size=5>{result['remaining_kwh']}</font> 度\n\n"
                        f"> 😱 **非常危险！** 为了避免突然断电，请尽快安排充电哦！\n\n"
                        f"***\n"
                        f"<font color='#808080' size=2>预警时间: {current_time}</font>"
                    )
                    print(f"发出低电量预警: {remaining_float} 度 < 10 度")
                    time.sleep(2) # 延迟一下，避免两条消息发送太快
                    send_to_dingtalk(alert_title, alert_message)
            except ValueError:
                print("❌ 解析剩余电量为数字时失败，无法进行低电量判断。")

        else:
            # --- 失败消息 ---
            title = f"查询失败 - {dorm['dorm_name']}"
            message = (
                f"### 🚨 {title}\n\n"
                f"小助手没能成功获取到 **{dorm['dorm_name']}** 的电费信息。\n\n"
                f"**失败详情**:\n"
                f"> {error}\n\n"
                f"**可能原因**:\n"
                f"> 1. **`JSESSIONID` 过期了** (最常见！)。\n"
                f"> 2. 学校服务器暂时不稳定。\n\n"
                f"***\n"
                f"<font color='#808080' size=2>报告时间: {current_time}</font>"
            )
            print(f"❌ 查询失败: {dorm['dorm_name']}, 原因: {error}")
            send_to_dingtalk(title, message)
        
        # 两个寝室查询之间间隔几秒，避免请求过于频繁
        if len(DORM_LIST) > 1:
             time.sleep(3)
