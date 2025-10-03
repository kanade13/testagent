import os

class Settings:
    PROJECT_NAME = os.getenv("PROJECT_NAME", "testagent")
    API_V1_PREFIX = "/api/v1"
    API_KEY = os.getenv("API_KEY", "ustc")
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

settings = Settings()