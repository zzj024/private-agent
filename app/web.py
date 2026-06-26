# app/web.py
# 职责：返回静态 HTML 页面
# HTML 存于 static/index.html，避免 Python 字符串转义问题

from pathlib import Path


def get_html() -> str:
    html_path = Path(__file__).resolve().parent.parent / "static" / "index.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return "<h1>页面未找到</h1>"
