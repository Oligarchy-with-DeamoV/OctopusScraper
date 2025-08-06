# Processors 测试文档

## 概述

Processors 模块的测试覆盖了内容处理器的各个方面，包括 HTML 内容清理、LLM 增强处理、处理器链执行等功能的验证。

## 测试文件位置

- **主测试文件**: `tests/octopus_scraper/processors/test_html_processor.py`
- **LLM 测试**: `tests/octopus_scraper/processors/test_llm_processor.py`
- **集成测试**: `tests/octopus_scraper/test_processors_integration.py`
- **性能测试**: `tests/octopus_scraper/processors/test_processor_performance.py`

## 测试结构

### 单元测试

#### 测试类: `TestHTMLContentProcessor`

```python
class TestHTMLContentProcessor:
    """HTML 内容处理器测试"""

    def test_html_tag_removal(self):
        """测试 HTML 标签清理功能"""

    def test_content_extraction(self):
        """测试主要内容提取"""

    def test_whitespace_normalization(self):
        """测试空白字符标准化"""

    def test_link_preservation(self):
        """测试链接保留功能"""

    def test_image_handling(self):
        """测试图片处理"""

    def test_max_content_length(self):
        """测试内容长度限制"""

    def test_malformed_html(self):
        """测试格式错误的 HTML 处理"""

    def test_empty_content(self):
        """测试空内容处理"""
```

#### 测试类: `TestLLMProcessor`

```python
class TestLLMProcessor:
    """LLM 内容处理器测试"""

    def test_summary_generation(self):
        """测试摘要生成功能"""

    def test_tag_generation(self):
        """测试标签生成功能"""

    def test_api_error_handling(self):
        """测试 API 错误处理"""

    def test_content_length_limit(self):
        """测试内容长度限制"""

    def test_rate_limiting(self):
        """测试 API 速率限制处理"""

    def test_retry_mechanism(self):
        """测试重试机制"""

    def test_configuration_validation(self):
        """测试配置验证"""
```

### 集成测试

#### 测试类: `TestProcessorChain`

```python
class TestProcessorChain:
    """处理器链集成测试"""

    def test_sequential_processing(self):
        """测试顺序处理"""

    def test_error_propagation(self):
        """测试错误传播"""

    def test_partial_failure_handling(self):
        """测试部分失败处理"""

    def test_performance_with_chain(self):
        """测试处理链性能"""
```

## 测试用例详解

### HTML 内容处理器测试

#### 标签清理测试

```python
def test_html_tag_removal(self):
    """测试 HTML 标签清理功能"""
    processor = HTMLContentProcessor({
        "remove_tags": ["script", "style", "nav"]
    })
    
    html_content = """
    <html>
        <head>
            <script>alert('test');</script>
            <style>body { color: red; }</style>
        </head>
        <body>
            <nav>Navigation</nav>
            <main>
                <h1>Title</h1>
                <p>Content paragraph</p>
            </main>
        </body>
    </html>
    """
    
    content = Content(content_id="test", content=html_content)
    processed = processor.process(content)
    
    assert "<script>" not in processed.content
    assert "<style>" not in processed.content
    assert "<nav>" not in processed.content
    assert "<h1>Title</h1>" in processed.content
    assert "<p>Content paragraph</p>" in processed.content
```

#### 内容提取测试

```python
def test_content_extraction(self):
    """测试主要内容提取"""
    processor = HTMLContentProcessor({
        "extract_text_only": True
    })
    
    html_content = """
    <article>
        <h1>Article Title</h1>
        <p>First paragraph with <a href="#">link</a>.</p>
        <p>Second paragraph with <strong>bold text</strong>.</p>
    </article>
    """
    
    content = Content(content_id="test", content=html_content)
    processed = processor.process(content)
    
    expected_text = "Article Title\nFirst paragraph with link.\nSecond paragraph with bold text."
    assert processed.content.strip() == expected_text
```

### LLM 处理器测试

#### 摘要生成测试

```python
@pytest.mark.asyncio
async def test_summary_generation(self):
    """测试摘要生成功能"""
    # Mock LLM API 响应
    with patch('openai.ChatCompletion.create') as mock_openai:
        mock_openai.return_value = {
            'choices': [{
                'message': {
                    'content': 'This is a test summary of the article.'
                }
            }]
        }
        
        processor = LLMProcessor({
            "generate_summary": True,
            "api_key": "test_key",
            "model_name": "gpt-3.5-turbo"
        })
        
        content = Content(
            content_id="test",
            content="This is a long article about testing procedures..."
        )
        
        processed = await processor.process(content)
        
        assert processed.summary == "This is a test summary of the article."
        assert mock_openai.called
```

#### API 错误处理测试

```python
@pytest.mark.asyncio
async def test_api_error_handling(self):
    """测试 API 错误处理"""
    with patch('openai.ChatCompletion.create') as mock_openai:
        mock_openai.side_effect = openai.error.RateLimitError("Rate limit exceeded")
        
        processor = LLMProcessor({
            "generate_summary": True,
            "api_key": "test_key",
            "max_retries": 2
        })
        
        content = Content(content_id="test", content="Test content")
        
        # 应该优雅地处理错误，返回原始内容
        processed = await processor.process(content)
        
        assert processed.content == content.content
        assert processed.summary is None
```

### 处理器链测试

#### 顺序处理测试

```python
def test_sequential_processing(self):
    """测试顺序处理"""
    html_processor = HTMLContentProcessor({
        "remove_tags": ["script", "style"],
        "extract_text_only": False
    })
    
    llm_processor = LLMProcessor({
        "generate_summary": True,
        "generate_tags": True
    })
    
    html_content = """
    <article>
        <script>alert('test');</script>
        <h1>Test Article</h1>
        <p>This is test content for processing.</p>
    </article>
    """
    
    content = Content(content_id="test", content=html_content)
    
    # 第一步：HTML 处理
    content = html_processor.process(content)
    assert "<script>" not in content.content
    
    # 第二步：LLM 处理
    with patch('openai.ChatCompletion.create') as mock_openai:
        mock_openai.return_value = {
            'choices': [{'message': {'content': 'Test summary'}}]
        }
        
        content = llm_processor.process(content)
        assert content.summary == "Test summary"
```

## Mock 和 Fixture

### 通用 Fixture

```python
@pytest.fixture
def sample_html_content():
    """示例 HTML 内容"""
    return """
    <html>
        <head>
            <title>Test Article</title>
            <script src="analytics.js"></script>
        </head>
        <body>
            <header>
                <nav>Navigation menu</nav>
            </header>
            <main>
                <article>
                    <h1>Main Article Title</h1>
                    <p>First paragraph with <a href="#">important link</a>.</p>
                    <p>Second paragraph with <strong>emphasis</strong>.</p>
                    <img src="image.jpg" alt="Test image">
                </article>
            </main>
            <footer>Footer content</footer>
        </body>
    </html>
    """

@pytest.fixture
def html_processor_config():
    """HTML 处理器配置"""
    return {
        "remove_tags": ["script", "nav", "footer"],
        "preserve_links": True,
        "extract_images": False,
        "max_content_length": 5000
    }

@pytest.fixture
def llm_processor_config():
    """LLM 处理器配置"""
    return {
        "api_key": "test_openai_key",
        "model_name": "gpt-3.5-turbo",
        "generate_summary": True,
        "generate_tags": True,
        "max_tokens": 150,
        "temperature": 0.7
    }
```

### Mock LLM API

```python
@pytest.fixture
def mock_openai_api():
    """Mock OpenAI API 响应"""
    with patch('openai.ChatCompletion.create') as mock:
        mock.return_value = {
            'choices': [{
                'message': {
                    'content': 'Generated summary content'
                }
            }],
            'usage': {
                'total_tokens': 150
            }
        }
        yield mock

@pytest.fixture
def mock_openai_error():
    """Mock OpenAI API 错误"""
    with patch('openai.ChatCompletion.create') as mock:
        mock.side_effect = openai.error.RateLimitError("Rate limit exceeded")
        yield mock
```

## 性能测试

### 处理速度测试

```python
def test_html_processing_performance(html_processor, sample_html_content):
    """测试 HTML 处理性能"""
    content = Content(content_id="perf_test", content=sample_html_content * 100)
    
    start_time = time.time()
    processed = html_processor.process(content)
    end_time = time.time()
    
    processing_time = end_time - start_time
    
    # 应该在合理时间内完成处理
    assert processing_time < 1.0
    assert len(processed.content) > 0
```

### 内存使用测试

```python
def test_memory_usage_with_large_content():
    """测试大内容处理的内存使用"""
    import psutil
    import os
    
    process = psutil.Process(os.getpid())
    initial_memory = process.memory_info().rss
    
    # 处理大量内容
    large_content = "<p>Test content</p>" * 10000
    processor = HTMLContentProcessor({})
    
    for _ in range(100):
        content = Content(content_id=f"test_{_}", content=large_content)
        processor.process(content)
    
    final_memory = process.memory_info().rss
    memory_increase = final_memory - initial_memory
    
    # 内存增长应该在合理范围内
    assert memory_increase < 100 * 1024 * 1024  # 100MB
```

## 测试运行

### 运行所有处理器测试

```bash
# 运行所有处理器测试
poetry run pytest tests/octopus_scraper/processors/ -v

# 运行 HTML 处理器测试
poetry run pytest tests/octopus_scraper/processors/test_html_processor.py -v

# 运行 LLM 处理器测试
poetry run pytest tests/octopus_scraper/processors/test_llm_processor.py -v
```

### 运行性能测试

```bash
# 运行性能测试
poetry run pytest tests/octopus_scraper/processors/test_processor_performance.py -v

# 运行带有性能分析的测试
poetry run pytest tests/octopus_scraper/processors/ --profile
```

### 运行覆盖率测试

```bash
# 生成测试覆盖率报告
poetry run pytest tests/octopus_scraper/processors/ --cov=octopus_scraper.processors --cov-report=html
```

## 测试数据

### 示例 HTML 内容

```html
<!-- 标准文章格式 -->
<article>
    <header>
        <h1>Article Title</h1>
        <time>2024-01-01</time>
    </header>
    <div class="content">
        <p>First paragraph of content.</p>
        <p>Second paragraph with <a href="#">link</a>.</p>
    </div>
</article>

<!-- 复杂 HTML 结构 -->
<div class="complex-layout">
    <aside class="sidebar">Sidebar content</aside>
    <main>
        <article>
            <h1>Main Content</h1>
            <div class="meta">
                <span class="author">Author Name</span>
                <span class="date">2024-01-01</span>
            </div>
            <div class="body">
                <p>Article body content with <strong>formatting</strong>.</p>
            </div>
        </article>
    </main>
</div>
```

### 环境变量测试

```python
@pytest.fixture
def mock_env_vars(monkeypatch):
    """Mock 环境变量"""
    monkeypatch.setenv("OPENAI_API_KEY", "test_key")
    monkeypatch.setenv("LLM_MODEL_NAME", "gpt-3.5-turbo")
    monkeypatch.setenv("MAX_CONTENT_LENGTH", "5000")
```

## 故障排除

### 常见测试问题

#### 1. LLM API 测试失败

```python
# 确保正确 Mock API 调用
with patch('octopus_scraper.processors.llm_processor.openai.ChatCompletion.create') as mock:
    # 设置 Mock 响应
    pass
```

#### 2. HTML 解析错误

```python
# 使用有效的 HTML 测试数据
html_content = "<html><body><p>Valid content</p></body></html>"
```

#### 3. 性能测试不稳定

```python
# 使用相对性能阈值而不是绝对时间
processing_time_per_item = total_time / item_count
assert processing_time_per_item < max_acceptable_time
```

## 测试最佳实践

### 1. 测试隔离

- 每个测试用例都应该独立运行
- 使用 fixture 提供一致的测试数据
- Mock 外部 API 调用

### 2. 边界条件测试

- 测试空内容处理
- 测试超大内容处理
- 测试格式错误的输入

### 3. 错误场景覆盖

- API 调用失败
- 网络超时
- 配置错误

### 4. 性能验证

- 设置合理的性能基准
- 监控内存使用
- 测试并发处理能力

## 相关文档

- [Processors 模型文档](./processors.md) - 了解处理器的架构和实现
- [TaskManager 测试文档](../task_manager/task-manager-testing.md) - 了解任务系统的测试
- [Scrapers 测试文档](../scrapers/scrapers-testing.md) - 了解抓取器的测试方法
