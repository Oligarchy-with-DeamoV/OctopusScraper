package processor

import (
	"context"
	"errors"
	"log/slog"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/content"
)

const (
	ProcessorHTMLContent = "html_content"
	ProcessorLLMSummary  = "llm_summary"
	ProcessorLLMKeywords = "llm_keywords"
	ProcessorLLMTags     = "llm_tags"
)

var (
	ErrUnsupportedProcessor = errors.New("unsupported processor")
	supportedProcessors     = []string{
		ProcessorHTMLContent,
		ProcessorLLMSummary,
		ProcessorLLMKeywords,
		ProcessorLLMTags,
	}
)

// Processor transforms content while preserving item ordering.
type Processor interface {
	Name() string
	Priority() int
	Process(context.Context, []content.Content) ([]content.Content, error)
}

// Factory creates a processor from its YAML configuration.
type Factory interface {
	Create(name string, rawConfig map[string]any) (Processor, error)
	Supported(name string) bool
}

// SupportedProcessors returns the only processor names accepted by the Go runtime.
func SupportedProcessors() []string {
	out := make([]string, len(supportedProcessors))
	copy(out, supportedProcessors)
	return out
}

type baseProcessor struct {
	name     string
	priority int
	logger   *slog.Logger
}

func (p baseProcessor) Name() string {
	return p.name
}

func (p baseProcessor) Priority() int {
	return p.priority
}

func (p baseProcessor) logFailure(item content.Content, err error) {
	if p.logger == nil {
		return
	}
	p.logger.Error(
		"Content processor failed",
		"processor", p.name,
		"content_id", item.ContentID,
		"link", item.Link,
		"error", err,
	)
}

func (p baseProcessor) logFallback(item content.Content, err error) {
	if p.logger == nil {
		return
	}
	p.logger.Warn(
		"Content processor fallback used",
		"processor", p.name,
		"content_id", item.ContentID,
		"link", item.Link,
		"error", err,
	)
}

func processorLogger(loggers []*slog.Logger) *slog.Logger {
	for _, logger := range loggers {
		if logger != nil {
			return logger
		}
	}
	return nil
}
