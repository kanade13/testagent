import requests
from main_controller import CONTEXT_JSON
BASE_URL = "http://localhost:8000/api/v1"
API_KEY = "ustc"  

headers = {
    "Content-Type": "application/json",
    "X-API-Key": API_KEY
}

def test_health():
    url = f"{BASE_URL}/healthz"
    resp = requests.get(url, headers=headers)
    print("Health check:", resp.status_code, resp.json())

def test_run_case():
    url = f"{BASE_URL}/case/run"
    payload = {
        "case_name": "",
        "case_desc": "利用PXA工具进行3DMark的SteelNormadDX12场景的Stress测试，用窗口模式，测试时长240分钟",
        "context_json": CONTEXT_JSON,
        "model": "qwen3-235b-a22b-instruct-2507",
        "max_retries": 3,
        "context": None
    }
    resp = requests.post(url, headers=headers, json=payload)
    print("Run case:", resp.status_code, resp.json())

if __name__ == "__main__":
    test_health()
    test_run_case()
