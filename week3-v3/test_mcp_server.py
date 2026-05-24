"""MCP Knowledge Server 测试脚本。

通过 stdin/stdout 模拟 MCP 客户端与服务器通信。
"""

import json
import subprocess
import sys


def send_and_receive(proc: subprocess.Popen, request: dict) -> dict | None:
    """发送请求并接收响应。"""
    message = json.dumps(request, ensure_ascii=False) + "\n"
    proc.stdin.write(message.encode())
    proc.stdin.flush()

    response_line = proc.stdout.readline()
    if response_line:
        return json.loads(response_line)
    return None


def main() -> None:
    """测试 MCP Server 的三个核心功能。"""
    proc = subprocess.Popen(
        [sys.executable, "mcp_knowledge_server.py"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
    )

    try:
        # 1. 测试 initialize
        print("=" * 50)
        print("测试 initialize")
        resp = send_and_receive(proc, {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {},
        })
        print(json.dumps(resp, indent=2, ensure_ascii=False))

        # 发送 initialized 通知
        proc.stdin.write(json.dumps({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        }).encode() + b"\n")
        proc.stdin.flush()

        # 2. 测试 tools/list
        print("\n" + "=" * 50)
        print("测试 tools/list")
        resp = send_and_receive(proc, {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        })
        tools = resp.get("result", {}).get("tools", [])
        for tool in tools:
            print(f"  - {tool['name']}: {tool['description']}")

        # 3. 测试 search_articles
        print("\n" + "=" * 50)
        print("测试 search_articles (keyword='agent')")
        resp = send_and_receive(proc, {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "search_articles",
                "arguments": {"keyword": "agent", "limit": 3},
            },
        })
        content = resp.get("result", {}).get("content", [{}])[0].get("text", "")
        results = json.loads(content)
        print(f"  找到 {len(results)} 篇文章:")
        for article in results:
            print(f"    - [{article['id']}] {article['title']} (score: {article['score']})")

        # 4. 测试 get_article
        print("\n" + "=" * 50)
        print("测试 get_article (id='github-20260505-001')")
        resp = send_and_receive(proc, {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "get_article",
                "arguments": {"article_id": "github-20260505-001"},
            },
        })
        content = resp.get("result", {}).get("content", [{}])[0].get("text", "")
        article = json.loads(content)
        print(f"  标题: {article.get('title')}")
        print(f"  来源: {article.get('source_type')}")
        print(f"  标签: {', '.join(article.get('tags', []))}")

        # 5. 测试 knowledge_stats
        print("\n" + "=" * 50)
        print("测试 knowledge_stats")
        resp = send_and_receive(proc, {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "knowledge_stats",
                "arguments": {},
            },
        })
        content = resp.get("result", {}).get("content", [{}])[0].get("text", "")
        stats = json.loads(content)
        print(f"  文章总数: {stats['total_articles']}")
        print(f"  来源分布: {stats['source_distribution']}")
        print(f"  平均评分: {stats['average_score']}")
        print(f"  热门标签: {[t['tag'] for t in stats['top_tags'][:5]]}")

        print("\n" + "=" * 50)
        print("所有测试通过！")

    finally:
        proc.terminate()
        proc.wait()


if __name__ == "__main__":
    main()
