import os, pathlib
from dotenv import load_dotenv, dotenv_values, find_dotenv

env_path = find_dotenv(usecwd=True) or str(pathlib.Path("/home/lb/.env"))
print("[DEBUG] env_path =", env_path)

# 先看 python-dotenv 实际解析到了什么（不依赖环境变量）
parsed = dotenv_values(env_path)
print("[DEBUG] parsed keys =", list(parsed.keys()))
print("[DEBUG] parsed OPENAI_BASE_URL =", parsed.get("OPENAI_BASE_URL"))
print("[DEBUG] parsed OPENAI_API_KEY  =", (parsed.get("OPENAI_API_KEY") or "")[:4] + "...")

# 然后真正注入到进程环境里（强制覆盖）
load_dotenv(dotenv_path=env_path, override=True)

base_url = os.getenv("OPENAI_BASE_URL")
api_key  = os.getenv("OPENAI_API_KEY")
print("[DEBUG] env OPENAI_BASE_URL =", base_url)
print("[DEBUG] env OPENAI_API_KEY  =", (api_key or "")[:4] + "...", "len=", len(api_key or ""))

assert api_key, "仍未读到 API KEY，请回看上面 parsed 的输出确认 .env 内容是否被正确解析。"
