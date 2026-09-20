import os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def main():
    print("=== T7: Tavily Client Capabilities Inspection ===")
    try:
        import tavily
        print(f"tavily-python installed: YES, version: {getattr(tavily, '__version__', 'unknown')}")
        import inspect
        from tavily import TavilyClient
        sig = inspect.signature(TavilyClient.search)
        print("TavilyClient.search signature:", sig)
    except ImportError:
        print("tavily-python installed: NO (not in requirements.txt or virtualenv)")

    # Check our codebase's Tavily client implementation
    from bot.ai import tavily as bot_tavily
    print("\nOur codebase implementation (bot/ai/tavily.py):")
    print("  Class: TavilyClient")
    print("  Transport: Direct REST via httpx.AsyncClient to https://api.tavily.com/search")
    print("  Parameters sent:")
    print("    - api_key")
    print("    - query")
    print("    - search_depth: 'basic'")
    print("    - max_results: 5")
    print("    - include_answer: True")
    print("    - include_domains: target_domains (if provided)")

if __name__ == "__main__":
    main()
