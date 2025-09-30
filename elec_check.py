# 导入所需库
import requests
import json
import urllib.parse
import re
import time
import hmac
import hashlib
import base64
import os

# --- 1. 配置区域：从 GitHub Secrets (环境变量) 读取信息 ---

# 钉钉机器人配置
# 这些值将由 GitHub Actions 从仓库的 Secrets 中自动注入
DINGTALK_WEBHOOK = os.environ.get('DINGTALK_WEBHOOK')
DINGTALK_SECKEY = os.environ.get('DINGTALK_SECKEY')

# 电费查询配置
JSESSIONID = os.environ.get('JSESSIONID')

# 检查所有必要的 Secrets 是否已成功加载
if not all([DINGTALK_WEBHOOK, DINGTALK_SECKEY, JSESSIONID]):
    print("❌ 错误：一个或多个必要的 Secrets 未配置或加载失败。")
    print("请检查 GitHub 仓库的 'Settings > Secrets and variables > Actions' 中是否已正确设置以下 Secrets：")
    print("DINGTALK_WEBHOOK, DINGTALK_SECKEY, JSESSIONID")
    exit(1) # 退出脚本，防止后续错误

# 查询参数 (这部分信息不敏感，可以直接保留在代码中)
QUERY_PAYLOAD = {
    "query_elec_roominfo": {
        "aid": "0030000000006001",
        "account": "26577",
        "room": {
            "roomid": "20161009111811624619",
            "room": "1栋609"
        },
        "floor": {
            "floorid": "6",
            "floor": "6层"
        },
        "area": {
            "area": "天津工业大学",
            "areaname": "天津工业大学"
        },
        "building": {
            "buildingid": "20161008184448464922",
            "building": "西苑7号楼"
        }
    }
}

# --- 配置区域结束 ---


def get_electricity_info():
    """发送请求获取电费信息"""
    url = "http://wxjdf.tiangong.edu.cn:9910/web/Common/Tsm.html"
    
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Cookie': f'JSESSIONID={JSESSIONID}',
        'User-Agent': 'Mozilla/5.0 (Linux; Android 12; SM-F926U Build/V417IR; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/101.0.4951.61 Safari/537.36',
    }
    
    # 构造请求体
    jsondata_str = json.dumps(QUERY_PAYLOAD)
    jsondata_encoded = urllib.parse.quote(jsondata_str)
    form_data = {
        'jsondata': jsondata_encoded,
        'funname': 'synjones.onecard.query.elec.roominfo',
        'json': 'true'
    }
    
    try:
        response = requests.post(url, headers=headers, data=form_data, timeout=10)
        response.raise_for_status()
        result = response.json()
        
        if result.get("query_elec_roominfo", {}).get("retcode") == "0":
            errmsg = result["query_elec_roominfo"]["errmsg"]
            match = re.search(r'剩余购电量:(\d+\.?\d*)度', errmsg)
            if match:
                remaining_kwh = match.group(1)
                room_info = f"{QUERY_PAYLOAD['query_elec_roominfo']['building']['building']} {QUERY_PAYLOAD['query_elec_roominfo']['room']['room']}"
                return room_info, remaining_kwh
            else:
                return None, f"解析电量信息失败: {errmsg}"
        else:
            errmsg = result.get("query_elec_roominfo", {}).get("errmsg", "未知错误，可能是JSESSIONID已过期")
            return None, f"查询失败: {errmsg}"

    except requests.exceptions.RequestException as e:
        return None, f"网络请求异常: {e}"
    except json.JSONDecodeError:
        return None, "服务器返回数据格式非JSON，无法解析"


def send_to_dingtalk(title, text):
    """发送消息到钉钉机器人 (使用加签方式)"""
    timestamp = str(round(time.time() * 1000))
    secret_enc = DINGTALK_SECKEY.encode('utf-8')
    string_to_sign = f'{timestamp}\n{DINGTALK_SECKEY}'
    string_to_sign_enc = string_to_sign.encode('utf-8')
    hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    
    signed_url = f"{DINGTALK_WEBHOOK}&timestamp={timestamp}&sign={sign}"
    
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": title,
            "text": text
        }
    }
    
    try:
        response = requests.post(signed_url, headers={'Content-Type': 'application/json'}, data=json.dumps(payload), timeout=10)
        result = response.json()
        if result.get("errcode") == 0:
            print("✅ 钉钉消息发送成功！")
        else:
            print(f"❌ 钉钉消息发送失败: {result.get('errmsg')}")
    except requests.exceptions.RequestException as e:
        print(f"❌ 发送钉钉消息时网络异常: {e}")


if __name__ == "__main__":
    print("🚀 开始查询电费...")
    room_info, data = get_electricity_info()
    
    if room_info:
        title = "寝室电费提醒"
        message_text = (
            f"### ⚡ 电费实时查询\n\n"
            f"**查询寝室**: {room_info}\n\n"
            f"**剩余电量**: <font color='#008000' size=5>{data}</font> 度\n\n"
            f"***\n"
            f"<font color='#808080' size=2>请留意电量，及时充电哦～</font>"
        )
        print(f"查询成功: {room_info}, 剩余电量: {data} 度")
        send_to_dingtalk(title, message_text)
    else:
        title = "电费查询失败"
        message_text = (
            f"### ⚠️ 电费查询失败\n\n"
            f"**失败原因**: {data}"
        )
        print(f"查询失败: {data}")
        send_to_dingtalk(title, message_text)