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

# 从 .env 里取出配置
VOLCENGINE_API_KEY = os.getenv("VOLCENGINE_API_KEY")
VOLCENGINE_BASE_URL = os.getenv("VOLCENGINE_BASE_URL")
MODEL_ID = os.getenv("MODEL")
MAX_TOKENS = os.getenv("MAX_TOKENS")
# 深度思考开关：enabled / disabled。方舟的 economic 版默认开启，关掉能省很多输出 token
THINKING = os.getenv("THINKING", "disabled").strip().lower()


def get_model(model_id=None, temperature=None):
    """创建一个模型对象。

    model_id 传了就优先用它，否则用 .env 里的 MODEL。
    """
    return init_chat_model(
        model="openai:" + (model_id or MODEL_ID),
        temperature=temperature,
        api_key=VOLCENGINE_API_KEY,
        base_url=VOLCENGINE_BASE_URL,
        max_tokens=int(MAX_TOKENS) if MAX_TOKENS else 4096,
        # 方舟的 thinking 是请求体里的顶层字段，必须走 extra_body 才能发出去；
        # 直接当关键字参数传（thinking=...）会被 LangChain 塞进 model_kwargs 并报警告
        extra_body={"thinking": {"type": THINKING}},
    )
