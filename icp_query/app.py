import os
import hashlib
import time
import requests
import urllib3
from urllib.parse import urlencode
from typing import Dict, List
from loguru import logger
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from datetime import datetime

# 禁用警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 创建日志目录
log_directory = "log"
if not os.path.exists(log_directory):
    os.makedirs(log_directory)

# 配置日志
logger.add(os.path.join(log_directory, "icp_{time:YYYY.MM.DD}.log"), 
           rotation="1 day",  # 每天生成一个新日志文件
           retention="180 days",  # 保留180天的日志
           format="{time} - {level} - {message}",  # 日志格式
           level="INFO")  # 日志级别

class ICPClient:
    def __init__(self):
        self._get_token_url = "https://hlwicpfwc.miit.gov.cn/icpproject_query/api/auth"
        self._query_url = "https://hlwicpfwc.miit.gov.cn/icpproject_query/api/icpAbbreviateInfo/queryByCondition/"
        
        self.token = ""
        self.refresh_token = ""
        self.expire_in = 0
        self.sign = "eyJ0eXBlIjozLCJleHREYXRhIjp7InZhZnljb2RlX2ltYWdlX2tleSI6IjBlNzg0YzM4YmQ1ZTQwNWY4NzQyMTdiN2E5MjVjZjdhIn0sImUiOjE3MzA5NzkzNTgwMDB9.kyklc3fgv9Ex8NnlmkYuCyhe8vsLrXBcUUkEawZryGc"
        self._referer = "https://beian.miit.gov.cn/"

        logger.info("ICPClient initialized.")

    def _get_proxies(self, api_url: str) -> Dict[str, str]:
        try:
            ip = requests.get(api_url, timeout=3).text.strip()
            logger.info(f"使用代理 IP: {ip}")
            return {
                "http": f"http://{ip}",
                "https": f"http://{ip}"
            }
        except Exception as e:
            logger.error(f"获取代理失败: {e}")
            raise Exception(f"获取代理失败: {e}")

    def _refresh_token(self, proxies: Dict[str, str]):
        current_ts = int(time.time() * 1000)
        timestamp_str = str(current_ts)
        auth_key = hashlib.md5(f"testtest{timestamp_str}".encode()).hexdigest()

        headers = {
            "Host": "hlwicpfwc.miit.gov.cn",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": self._referer,
            "Cookie": "__jsluid_s=6452684553c30942fcb8cff8d5aa5a5b",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
        }

        data = urlencode({
            "authKey": auth_key,
            "timeStamp": timestamp_str
        })

        try:
            response = requests.post(
                self._get_token_url,
                headers=headers,
                data=data,
                proxies=proxies,
                timeout=10,
                verify=False
            )
            response.raise_for_status()
            json_data = response.json()

            if json_data.get("code") != 200:
                raise Exception(json_data.get("msg", "Token刷新失败"))

            self.expire_in = current_ts + json_data["params"]["expire"]
            self.token = json_data["params"]["bussiness"]
            self.refresh_token = json_data["params"]["refresh"]
            logger.info("Token refreshed successfully.")

        except Exception as e:
            logger.error(f"Token刷新失败: {str(e)}")
            raise Exception(f"Token刷新失败: {str(e)}")

    def query(self, keyword: str, proxy_api: str = None) -> Dict:
        if not proxy_api:
            logger.error("必须提供代理获取 API 地址")
            raise Exception("必须提供代理获取 API 地址")
        
        proxies = self._get_proxies(proxy_api)
        self._refresh_token(proxies)

        payload = {
            "pageNum": "1",
            "pageSize": "999",
            "serviceType": "1",
            "unitName": keyword
        }

        headers = {
            "Host": "hlwicpfwc.miit.gov.cn",
            "Token": self.token,
            "Sign": self.sign,
            "Referer": self._referer,
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            "Content-Type": "application/json",
            "Cookie": "__jsluid_s=8e209cf6c7c40f530a300ac8dd0eb6c7",
            "Accept-Encoding": "gzip",
            "Connection": "keep-alive"
        }

        try:
            logger.info(f"发送查询请求: {payload}")
            response = requests.post(
                self._query_url,
                headers=headers,
                json=payload,
                proxies=proxies,
                timeout=15,
                verify=False
            )
            response.raise_for_status()
            json_data = response.json()

            if json_data.get("code") != 200:
                raise Exception(json_data.get("msg", "查询请求失败"))

            return self._parse_response(json_data)

        except Exception as e:
            logger.error(f"查询失败: {str(e)}")
            raise Exception(f"查询失败: {str(e)}")

    def _parse_response(self, json_data: Dict) -> Dict:
        try:
            items: List[Dict] = []
            for item in json_data["params"]["list"]:
                items.append({
                    "serviceLicence": item.get("serviceLicence"),
                    "unitName": item.get("unitName"),
                    "domain": item.get("domain"),
                    "nature": item.get("natureName"),
                    "auditTime": item.get("updateRecordTime")
                })

            return {
                "total": json_data["params"]["total"],
                "items": items
            }
        except KeyError as e:
            logger.error(f"响应解析失败: {str(e)}")
            raise Exception(f"响应解析失败: {str(e)}")


# ---------------------------
# Flask 初始化
# ---------------------------
app = Flask(__name__)
CORS(app)

# 初始化客户端
client = ICPClient()


@app.route('/')
def index():
    return render_template('index.html')  # 确保 templates/index.html 存在


@app.route('/query', methods=['POST'])
def query():
    data = request.get_json()
    keyword = data.get('keyword')
    proxy_api = data.get('proxyApi')  # 接收用户传的代理 API 地址
    client_ip = request.remote_addr  # 获取请求的 IP 地址
    if not keyword:
        return jsonify({"error": "请输入关键词"}), 400

    try:
        logger.info(f"访问者 IP: {client_ip} 关键词: {keyword}")
        result = client.query(keyword, proxy_api)
        return jsonify(result)
    except Exception as e:
        logger.error(f"查询过程中发生错误: {str(e)}")
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
