import requests

#BASE_URL = "http://localhost:8000/"
BASE_URL = "http://112.29.111.158:20307/"

API_KEY = "ustc"

headers = {
    "Content-Type": "application/json",

}

def test_health():
    url = f"{BASE_URL}/healthz"
    resp = requests.get(url, headers=headers)
    print("Health check:", resp.status_code, safe_json(resp))

def test_run_case():
    url = f"{BASE_URL}/plan"
    payload = {
        "case_name": "",   
        "case_desc": "先把机器重启，然后跑Burnin测试30分钟，做1次S4，再跑burnin 30分钟",
        "user_input":""
    }
    #先把机器重启，然后跑Burnin测试30分钟，做1次S4，再跑burnin 30分钟
    resp = requests.post(url, headers=headers, json=payload)
    print("POST /plan status:", resp.status_code)
    data = safe_json(resp)
    if not resp.ok:
        raise RuntimeError(f"Create/Edit plan failed: {data}")
    thinking = data.get("thinking") or data.get("thinking_content")
    plan = data.get("plan")

    if plan is None:
        raise KeyError(f"Response JSON has no 'plan' key. Full body: {data}")

    return plan, thinking
def test_clear():
    resp=requests.post(url=f"{BASE_URL}/plan/clear")
    print("POST /plan status:", resp.status_code)
def safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return {"raw_text": resp.text}

if __name__ == "__main__":
    test_health()
    #test_clear()
    plan, thinking = test_run_case()
    from utils import json_pretty
    print("thinking：", thinking)
    print("初始测试计划：", json_pretty(plan))

