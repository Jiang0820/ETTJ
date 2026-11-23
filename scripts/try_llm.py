"""试跑脚本：直接运行本文件即可（PyCharm 右键 Run，或 python scripts/try_llm.py）。"""

import sys
from pathlib import Path

# 直接运行本文件时，把项目根目录放进 sys.path，才能 import ettj
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ettj.models import get_model


def main() -> None:
    model = get_model()  # 用 .env 里配置的模型
    reply = model.invoke("你好")
    print(reply.content)


if __name__ == "__main__":
    main()
