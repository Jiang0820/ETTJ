"""模型层：连接火山方舟上的 DeepSeek 模型。

用法：
    from ettj.models import get_model

    model = get_model()          # 用 .env 里配置的模型
    model.invoke("你好")
"""

import os
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

# 读取项目根目录的 .env 文件
load_dotenv(override=True)

# 从 .env 里取出三项配置
VOLCENGINE_API_KEY = os.getenv("VOLCENGINE_API_KEY")
VOLCENGINE_BASE_URL = os.getenv("VOLCENGINE_BASE_URL")
MODEL_ID = os.getenv("MODEL")
MAX_TOKENS = os.getenv("MAX_TOKENS")
temperature = os.getenv("TEMPERATURE")

def get_model(model_id=None, temperature=None):
    """创建一个模型对象。"""
    return init_chat_model(
        model="openai:" + MODEL_ID,
        temperature=temperature,
        api_key=VOLCENGINE_API_KEY,
        base_url=VOLCENGINE_BASE_URL,
        max_tokens=MAX_TOKENS,
        extra_body={"thinking": {"type": "enabled"}},
    )
