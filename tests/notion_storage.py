# 主逻辑示例
import argparse
from src.octopus_scraper.scrapers.utils.notionAPI import NotionAPIConfig, NotionStorage


arg_parser = argparse.ArgumentParser()
arg_parser.add_argument("--NOTION_API_KEY", help="Notion API Key", type=str)
arg_parser.add_argument("--NOTION_DATABASE_ID", help="Notion Database ID", type=str)
arg_parser.add_argument("--URL", help="RSS URL", type=str)

if __name__ == "__main__":
    args = arg_parser.parse_args()
    config = {
        "api_key": args.NOTION_API_KEY,
        "database_id": args.NOTION_DATABASE_ID,
    }
    storage = NotionStorage(config)

    # rss_url = "https://www.owenyoung.com/atom.xml"
    latest_links = storage.parse_rss_feed(args.URL)

    for link in latest_links:
        print(f"processing {link}")
        if response := storage.parse_article_content(link):
            storage.store_content(response)