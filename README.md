# OctopusScraper
OctopusScraper 是一款多功能信息抓取工具，旨在通过高效的算法分析和处理各种媒体数据。它隶属于 [Podcast 矩阵生成项目](https://www.notion.so/1a2fee3943728058be3be79b782e1cf4?pvs=4)，但具备广泛的应用潜力，可以作为中间件为其他项目提供数据抓取和分析能力。OctopusScraper 灵活高效，能够为后续项目提供强大的支持，助力快速实现数据整合与分析，为各类项目赋能。

## Installation
```bash
poetry install
```
Note: 更多的安装信息可以使用 `-vvv` 来 debug。

## Usage
```bash
poetry run octopus_go
```

## Dev Dependencies
1. Pre-commit Installation
    ```bash
    brew install pre-commit
    ```
2. Mannually Check
    ```bash
    pre-commit run --all-files
    ```

## Obtain Notion API Key and Database ID
1. Notion Secrect 官方获取手册 [here](https://developers.notion.com/docs/create-a-notion-integration):
2. Database ID 官方获取手册 [here](https://developers.notion.com/docs/working-with-databases)

## Tests Check
为了本项目的持续可维护性，目前为强制测试覆盖率超过 80% 才能提交，测试方式如下。

1. 手动检查是否在环境变量中正确设置了 Notion 相关配置
    ```bash
    # .zshrc
    export NOTION_API_KEY=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
    export NOTION_DATABASE_ID=1ca2602c0dbf80e2a090f7116d8e6959
    ```

1. Pytest 检查不需要外部服务的测试用例
    ```bash
    poetry run pytest -m "not need_external_service" --cov=octopus_scraper ./tests/octopus_scraper/base_scraper_test.py
    ```
1. Pytest 检查需要外部服务的测试用例
    ```bash
    poetry run pytest -m "need_external_service" --cov=octopus_scraper --cov-fail-under=80 ./tests/octopus_scraper/base_scraper_test.py
    ```
