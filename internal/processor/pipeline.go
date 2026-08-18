package processor

import (
	"context"
	"fmt"
	"sort"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/content"
)

// Pipeline applies processors in ascending numeric priority.
type Pipeline struct {
	processors []Processor
}

func NewPipeline(processors ...Processor) *Pipeline {
	copied := make([]Processor, len(processors))
	copy(copied, processors)
	sort.SliceStable(copied, func(i, j int) bool {
		return copied[i].Priority() < copied[j].Priority()
	})
	return &Pipeline{processors: copied}
}

func BuildPipeline(factory Factory, raw map[string]map[string]any) (*Pipeline, error) {
	if factory == nil {
		factory = NewRegistry()
	}
	processors := make([]Processor, 0, len(raw))
	for name, cfg := range raw {
		processor, err := factory.Create(name, cfg)
		if err != nil {
			return nil, err
		}
		processors = append(processors, processor)
	}
	return NewPipeline(processors...), nil
}

func (p *Pipeline) Process(ctx context.Context, items []content.Content) ([]content.Content, error) {
	current := items
	var err error
	for _, processor := range p.processors {
		current, err = processor.Process(ctx, current)
		if err != nil {
			return nil, fmt.Errorf("processor %s failed: %w", processor.Name(), err)
		}
	}
	return current, nil
}

func (p *Pipeline) Processors() []Processor {
	copied := make([]Processor, len(p.processors))
	copy(copied, p.processors)
	return copied
}
