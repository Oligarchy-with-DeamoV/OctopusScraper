# LLM处理器集成测试

这个目录包含了LLM处理器的集成测试，这些测试会真正调用LLM服务来验证功能。

## 环境配置

测试需要的环境变量已经配置在 `.env` 文件中，包括：

```
GPT_TEMPERATURE=0.9
OPENAI_API_BASE=http://10.170.138.230:8888/v1
OPENAI_API_VERSION=2023-03-15-preview
OPENAI_API_KEY=none
OPENAI_DEPLOYMENT_NAME=devapi35
OPENAI_API_TYPE=local
OPENAI_MODEL_NAME=/root/local_gpt
```

## 运行测试

### 运行所有LLM集成测试

```bash
# 在项目根目录下运行
poetry run pytest tests/integrate_tests/llm_tests/ -v
```

### 运行特定的测试

```bash
# 只运行基本功能测试
poetry run pytest tests/integrate_tests/llm_tests/test_llm_processor_integration.py::TestLLMProcessorIntegration::test_llm_processor_basic_functionality -v

# 只运行结构化输出测试
poetry run pytest tests/integrate_tests/llm_tests/test_llm_processor_integration.py::TestLLMProcessorIntegration::test_llm_processor_with_structured_output -v
```

### 跳过需要外部服务的测试

如果你想跳过所有需要外部LLM服务的测试：

```bash
poetry run pytest tests/integrate_tests/llm_tests/ -v -m "not need_external_service"
```

### 只运行需要外部服务的测试

```bash
poetry run pytest tests/integrate_tests/llm_tests/ -v -m "need_external_service"
```

## 测试内容

1. **test_environment_variables_loaded**: 验证环境变量是否正确加载
2. **test_llm_processor_basic_functionality**: 测试基本的LLM处理功能
3. **test_llm_processor_with_structured_output**: 测试带结构化JSON输出的LLM处理
4. **test_llm_processor_multiple_contents**: 测试处理多个内容的能力
5. **test_llm_processor_error_handling**: 测试错误处理机制
6. **test_llm_processor_json_extraction**: 测试JSON代码块提取功能

## 注意事项

- 这些测试需要连接到实际的LLM服务，确保网络连接正常
- 测试可能需要较长时间，因为要等待LLM响应
- 如果LLM服务不可用，测试会自动跳过
- 使用 `-s` 参数可以看到测试过程中的打印输出：`poetry run pytest tests/integrate_tests/llm_tests/ -v -s`
