import requests
from main_controller import CONTEXT_JSON
BASE_URL = "http://localhost:8000/api/v1"
#BASE_URL = "http://112.29.111.158:20307/api/v1"

API_KEY = "ustc"  

headers = {
    "Content-Type": "application/json"
}

def test_health():
    url = f"{BASE_URL}/healthz"
    resp = requests.get(url, headers=headers)
    print("Health check:", resp.status_code, resp.json())

def test_run_case():
    url = f"{BASE_URL}/run/case/generate"
    payload = {
        "case_name": "",
        "case_desc": "利用PXA工具进行3DMark的SteelNormadDX12场景的Stress测试，用窗口模式，测试时长240分钟",
        "context_json": "",
        "model": "qwen3-235b-a22b-thinking-2507",
        "max_retries": 3,
        "context": None,
    }

    resp = requests.post(url, headers=headers, json=payload)
    resp.raise_for_status()
    data = resp.json()

    if not data.get("ok", False):
        raise RuntimeError(f"Server returned ok=False: {data}")

    # 首选规范键名，其次兼容旧错别字（防止线上未同步）
    thinking = data.get("thinking_content")
    if thinking is None:
        thinking = data.get("thingking_content")  # 兼容老返回

    plan = data["plan"]

    #print("Run case:", resp.status_code)
    #print("thinking:", thinking)
    #print("plan:", plan)
    print("*****************************************************************************************")
    # 视你的调用习惯返回
    return plan, thinking

def test_parse_command(plan):
    url = f"{BASE_URL}/run/case/parse_command"
    print("Plan to edit:", plan)
    payload = {
        "case_name": "",
        "case_desc": "利用PXA工具进行3DMark的SteelNormadDX12场景的Stress测试，用窗口模式，测试时长240分钟",
        "context_json": "",
        "model": "qwen3-235b-a22b-instruct-2507",
        "max_retries": 3,
        "context": None,
        "user_text": "请把第五步改为nightraid场景",
        "plan": plan
    }
    resp = requests.post(url, headers=headers, json=payload)
    print("Run case:", resp.status_code, resp.json())
def test_validate_plan(plan):
    url = f"{BASE_URL}/run/case/validate_plan"
    payload = {
        "case_name": "",
        "case_desc": "利用PXA工具进行3DMark的SteelNormadDX12场景的Stress测试，用窗口模式，测试时长240分钟",
        "context_json": "",
        "model": "qwen3-235b-a22b-instruct-2507",
        "max_retries": 3,
        "context": None,
        "plan": plan
    }
    resp = requests.post(url, headers=headers, json=payload)
    print("Validate plan:", resp.status_code, resp.json())
def test_answer(plan):
    url = f"{BASE_URL}/run/case/answer"
    payload = {
        "case_name": "",
        "case_desc": "利用PXA工具进行3DMark的SteelNormadDX12场景的Stress测试，用窗口模式，测试时长240分钟",
        "context_json": "",
        "model": "qwen3-235b-a22b-instruct-2507",
        "max_retries": 3,
        "context": None,
        "question": "为什么第五步是这样设置的?",
        "plan": plan,
        "target_step": 5
    }
    resp = requests.post(url, headers=headers, json=payload)
    print("Answer question:", resp.status_code, resp.json())
if __name__ == "__main__":
    test_health()
    plan,thinking=test_run_case()
    print("*****************************************************************************************")
    print("初始测试计划：", plan)
    print("*****************************************************************************************")
    print("thinking：", thinking)    
    test_validate_plan(plan)
    test_parse_command(plan)
    print("*****************************************************************************************")
    test_answer(plan)
