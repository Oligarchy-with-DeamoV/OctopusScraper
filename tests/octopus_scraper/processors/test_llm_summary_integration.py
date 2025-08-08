"""
Integration tests for LLM Summary Processor.

This module contains integration tests that verify the complete workflow
of the summary processor with real or realistic LLM responses.
"""

import os
import sys
from unittest.mock import Mock, patch

import pytest

# Add src to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from octopus_scraper.llm.client import LLMResponse
from octopus_scraper.llm.prompts import PromptManager
from octopus_scraper.processors.llm_summary_processor import LLMSummaryProcessor
from octopus_scraper.protos import Content


class TestLLMSummaryProcessorIntegration:
    """Integration tests for LLMSummaryProcessor."""

    @pytest.fixture
    def realistic_config(self):
        """Realistic processor configuration."""
        return {
            "model_name": "gpt-3.5-turbo",
            "max_tokens": 1000,
            "temperature": 0.7,
            "timeout": 30,
            "retry_times": 3,
            "max_summary_length": 150,
            "summary_style": "concise",
            "preserve_structure": False,
            "include_key_points": True,
            "priority": 100,
        }

    @pytest.fixture
    def real_content_samples(self):
        """Real-world content samples for testing."""
        return [
            Content(
                content_id="tech_article_1",
                title="The Future of Artificial Intelligence in Healthcare",
                link="https://example.com/ai-healthcare",
                summary="",
                content="""
                Artificial Intelligence (AI) is revolutionizing healthcare in unprecedented ways. 
                From diagnostic imaging to drug discovery, AI technologies are transforming how 
                medical professionals approach patient care. Machine learning algorithms can now 
                analyze medical images with accuracy comparable to human radiologists, often 
                detecting conditions that might be missed by the human eye.
                
                In drug discovery, AI is accelerating the identification of potential therapeutic 
                compounds, reducing the time and cost of bringing new medicines to market. 
                Companies like DeepMind have shown remarkable success in protein folding 
                prediction, which could lead to breakthroughs in understanding diseases and 
                developing treatments.
                
                However, the integration of AI in healthcare also raises important questions 
                about data privacy, algorithmic bias, and the need for regulatory frameworks 
                to ensure patient safety. As we move forward, it will be crucial to balance 
                innovation with responsible implementation.
                """,
                published="2025-01-01",
                author="Dr. Jane Smith",
            ),
            Content(
                content_id="chinese_article_1",
                title="人工智能在医疗领域的应用前景",
                link="https://example.com/ai-medical-zh",
                summary="",
                content="""
                人工智能技术正在医疗领域掀起一场革命。从疾病诊断到药物研发，
                AI技术正在改变医疗专业人士治疗患者的方式。机器学习算法现在可以
                分析医学影像，其准确性可与人类放射科医生相媲美，甚至能够发现
                人眼可能遗漏的病症。
                
                在药物研发方面，AI正在加速潜在治疗化合物的识别，减少新药上市
                所需的时间和成本。像DeepMind这样的公司在蛋白质折叠预测方面
                取得了显著成功，这可能会带来对疾病理解和治疗开发的突破。
                
                然而，AI在医疗领域的整合也引发了关于数据隐私、算法偏见和监管
                框架需求的重要问题，以确保患者安全。随着我们的前进，平衡创新
                与负责任的实施将至关重要。
                """,
                published="2025-01-01",
                author="张医生",
            ),
            Content(
                content_id="short_content_1",
                title="Brief Update",
                link="https://example.com/brief",
                summary="",
                content="This is a very short article that doesn't have much content.",
                published="2025-01-01",
                author="Short Author",
            ),
        ]

    def mock_llm_responses(self, messages):
        """Mock realistic LLM responses based on content."""
        # Extract content from messages to determine response type
        user_message = next(
            (msg["content"] for msg in messages if msg["role"] == "user"), ""
        )

        if "人工智能" in user_message:
            # Chinese content response
            return LLMResponse(
                success=True,
                content="人工智能技术正在医疗领域带来革命性变化，从诊断成像到药物发现都有重大突破，但同时也面临数据隐私和算法偏见等挑战。",
                metadata={"model": "gpt-3.5-turbo", "language": "zh"},
            )
        elif "Artificial Intelligence" in user_message:
            # English content response
            return LLMResponse(
                success=True,
                content="AI is transforming healthcare through advanced diagnostic imaging and accelerated drug discovery, while raising important questions about data privacy and algorithmic bias.",
                metadata={"model": "gpt-3.5-turbo", "language": "en"},
            )
        elif "short article" in user_message:
            # Short content response
            return LLMResponse(
                success=True,
                content="This is a brief summary of the short article content.",
                metadata={"model": "gpt-3.5-turbo", "language": "en"},
            )
        else:
            # Default response
            return LLMResponse(
                success=True,
                content="This is a generated summary of the provided content.",
                metadata={"model": "gpt-3.5-turbo"},
            )

    def test_complete_workflow_multiple_contents(
        self, realistic_config, real_content_samples
    ):
        """Test complete workflow with multiple realistic content samples."""
        mock_client = Mock()
        mock_client.health_check.return_value = True
        mock_client.generate.side_effect = (
            lambda messages, **kwargs: self.mock_llm_responses(messages)
        )

        with patch(
            "octopus_scraper.processors.llm_summary_processor.LLMClient",
            return_value=mock_client,
        ):
            processor = LLMSummaryProcessor(realistic_config)

            # Process all content samples
            results = processor(real_content_samples)

            # Verify results
            assert len(results) == len(real_content_samples)

            for i, result in enumerate(results):
                original = real_content_samples[i]

                # Basic validations
                assert result.content_id == original.content_id
                assert result.title == original.title
                assert result.link == original.link
                assert result.content == original.content
                assert result.published == original.published
                assert result.author == original.author

                # Summary should be updated and valid
                assert result.summary != original.summary
                assert len(result.summary) > 0
                assert (
                    len(result.summary) <= realistic_config["max_summary_length"] * 2
                )  # Allow some flexibility

    def test_different_summary_styles_integration(self, real_content_samples):
        """Test integration with different summary styles."""
        styles = ["concise", "detailed", "bullet_points"]

        for style in styles:
            config = {
                "model_name": "gpt-3.5-turbo",
                "max_tokens": 1000,
                "temperature": 0.7,
                "timeout": 30,
                "retry_times": 3,
                "max_summary_length": 200,
                "summary_style": style,
                "preserve_structure": False,
                "include_key_points": True,
                "priority": 100,
            }

            mock_client = Mock()
            mock_client.health_check.return_value = True

            # Customize response based on style
            if style == "bullet_points":
                mock_client.generate.return_value = LLMResponse(
                    success=True,
                    content="• First key point of the article\n• Second important aspect\n• Third main conclusion",
                    metadata={"style": style},
                )
            elif style == "detailed":
                mock_client.generate.return_value = LLMResponse(
                    success=True,
                    content="This is a detailed summary that includes more comprehensive information about the article's main points, supporting evidence, and broader implications for the field.",
                    metadata={"style": style},
                )
            else:  # concise
                mock_client.generate.return_value = LLMResponse(
                    success=True,
                    content="Brief summary capturing the essential points of the article.",
                    metadata={"style": style},
                )

            with patch(
                "octopus_scraper.processors.llm_summary_processor.LLMClient",
                return_value=mock_client,
            ):
                processor = LLMSummaryProcessor(config)

                # Test with first content sample
                result = processor([real_content_samples[0]])

                assert len(result) == 1
                assert len(result[0].summary) > 0

    def test_error_recovery_integration(self, realistic_config, real_content_samples):
        """Test error recovery in integration scenarios."""
        mock_client = Mock()
        mock_client.health_check.return_value = True

        # Simulate intermittent failures
        call_count = 0

        def side_effect_with_failures(messages, **kwargs):
            nonlocal call_count
            call_count += 1

            if call_count == 2:  # Fail on second call
                return LLMResponse(success=False, error="Temporary API error")
            else:
                return self.mock_llm_responses(messages)

        mock_client.generate.side_effect = side_effect_with_failures

        with patch(
            "octopus_scraper.processors.llm_summary_processor.LLMClient",
            return_value=mock_client,
        ):
            processor = LLMSummaryProcessor(realistic_config)

            # Process content - should handle failures gracefully
            results = processor(real_content_samples)

            # All content should be processed (with fallbacks for failures)
            assert len(results) == len(real_content_samples)

            # All results should have some summary
            for result in results:
                assert len(result.summary) > 0

    def test_prompt_manager_integration(self, realistic_config):
        """Test integration with prompt manager."""
        mock_client = Mock()
        mock_client.health_check.return_value = True
        mock_client.generate.return_value = LLMResponse(
            success=True,
            content="Test summary from prompt manager integration.",
            metadata={"source": "prompt_manager"},
        )

        with patch(
            "octopus_scraper.processors.llm_summary_processor.LLMClient",
            return_value=mock_client,
        ):
            processor = LLMSummaryProcessor(realistic_config)

            # Test prompt manager functionality
            prompt_manager = processor.prompt_manager

            # Test creating messages
            messages = prompt_manager.create_summary_messages(
                title="Test Title",
                content="Test content for prompt generation.",
                style="concise",
                language="en",
                max_length=100,
            )

            assert len(messages) == 2  # System and user messages
            assert messages[0]["role"] == "system"
            assert messages[1]["role"] == "user"
            assert "Test Title" in messages[1]["content"]
            assert "Test content" in messages[1]["content"]

    def test_multilingual_content_processing(
        self, realistic_config, real_content_samples
    ):
        """Test processing content in different languages."""
        mock_client = Mock()
        mock_client.health_check.return_value = True
        mock_client.generate.side_effect = (
            lambda messages, **kwargs: self.mock_llm_responses(messages)
        )

        with patch(
            "octopus_scraper.processors.llm_summary_processor.LLMClient",
            return_value=mock_client,
        ):
            processor = LLMSummaryProcessor(realistic_config)

            # Process multilingual content
            results = processor(real_content_samples)

            # Find English and Chinese results
            english_result = next(
                r for r in results if r.content_id == "tech_article_1"
            )
            chinese_result = next(
                r for r in results if r.content_id == "chinese_article_1"
            )

            # Both should have valid summaries
            assert len(english_result.summary) > 0
            assert len(chinese_result.summary) > 0

            # Summaries should be different (language-appropriate)
            assert english_result.summary != chinese_result.summary

    def test_performance_with_large_batch(self, realistic_config):
        """Test processor performance with larger batch of content."""
        # Create a larger batch of content
        large_batch = []
        for i in range(10):
            content = Content(
                content_id=f"batch_test_{i}",
                title=f"Test Article {i}",
                link=f"https://example.com/article-{i}",
                summary="",
                content=f"This is test article number {i} with sufficient content for summary generation. "
                * 15,
                published="2025-01-01",
                author=f"Author {i}",
            )
            large_batch.append(content)

        mock_client = Mock()
        mock_client.health_check.return_value = True
        mock_client.generate.return_value = LLMResponse(
            success=True,
            content="Generated summary for batch processing test.",
            metadata={"batch": True},
        )

        with patch(
            "octopus_scraper.processors.llm_summary_processor.LLMClient",
            return_value=mock_client,
        ):
            processor = LLMSummaryProcessor(realistic_config)

            # Process large batch
            results = processor(large_batch)

            # Verify all items processed
            assert len(results) == len(large_batch)

            # Verify all have summaries
            for result in results:
                assert len(result.summary) > 0

            # Check that LLM was called for each item (no unexpected caching)
            assert mock_client.generate.call_count == len(large_batch)


if __name__ == "__main__":
    # Run integration tests
    pytest.main([__file__, "-v"])
