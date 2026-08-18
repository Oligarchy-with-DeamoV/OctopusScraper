package observability

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"os"
	"strings"
	"sync"
	"time"
)

func NewLogger(levelText, format string) (*slog.Logger, error) {
	level, err := parseLevel(levelText)
	if err != nil {
		return nil, err
	}
	format = strings.ToLower(strings.TrimSpace(format))
	if format == "" {
		format = "plain"
	}
	if format != "plain" && format != "json" {
		return nil, fmt.Errorf("unsupported log format: %s", format)
	}
	options := &slog.HandlerOptions{
		Level: level,
		ReplaceAttr: func(_ []string, attr slog.Attr) slog.Attr {
			switch attr.Key {
			case slog.LevelKey:
				if level, ok := attr.Value.Any().(slog.Level); ok {
					attr.Value = slog.StringValue(consoleLevel(level))
				} else {
					attr.Value = slog.StringValue(
						strings.ToLower(attr.Value.String()),
					)
				}
			case slog.MessageKey:
				attr.Key = "event"
			}
			return attr
		},
	}
	if format == "json" {
		return slog.New(slog.NewJSONHandler(os.Stdout, options)), nil
	}
	return slog.New(&consoleHandler{
		writer: os.Stdout,
		level:  level,
		attrs:  nil,
		mu:     &sync.Mutex{},
	}), nil
}

func parseLevel(value string) (slog.Level, error) {
	switch strings.ToUpper(strings.TrimSpace(value)) {
	case "DEBUG":
		return slog.LevelDebug, nil
	case "INFO", "":
		return slog.LevelInfo, nil
	case "WARNING", "WARN":
		return slog.LevelWarn, nil
	case "ERROR":
		return slog.LevelError, nil
	case "CRITICAL":
		return slog.LevelError + 4, nil
	default:
		return slog.LevelInfo, fmt.Errorf("unsupported log level: %s", value)
	}
}

type consoleHandler struct {
	writer io.Writer
	level  slog.Level
	attrs  []slog.Attr
	group  string
	mu     *sync.Mutex
}

var fallbackConsoleMutex sync.Mutex

func (h *consoleHandler) Enabled(_ context.Context, level slog.Level) bool {
	return level >= h.level
}

func (h *consoleHandler) Handle(_ context.Context, record slog.Record) error {
	values := make([]slog.Attr, 0, len(h.attrs)+record.NumAttrs())
	values = append(values, h.attrs...)
	record.Attrs(func(attr slog.Attr) bool {
		values = appendConsoleAttr(values, h.group, attr)
		return true
	})
	mutex := h.mu
	if mutex == nil {
		mutex = &fallbackConsoleMutex
	}
	mutex.Lock()
	defer mutex.Unlock()
	if _, err := fmt.Fprintf(
		h.writer,
		"%s [%s] %s",
		record.Time.Format(time.RFC3339),
		consoleLevel(record.Level),
		record.Message,
	); err != nil {
		return err
	}
	for _, attr := range values {
		if attr.Equal(slog.Attr{}) {
			continue
		}
		value := encodeConsoleValue(attr.Value)
		if _, err := fmt.Fprintf(h.writer, " %s=%s", attr.Key, value); err != nil {
			return err
		}
	}
	_, err := fmt.Fprintln(h.writer)
	return err
}

func (h *consoleHandler) WithAttrs(attrs []slog.Attr) slog.Handler {
	resolved := append([]slog.Attr(nil), h.attrs...)
	for _, attr := range attrs {
		resolved = appendConsoleAttr(resolved, h.group, attr)
	}
	return &consoleHandler{
		writer: h.writer,
		level:  h.level,
		attrs:  resolved,
		group:  h.group,
		mu:     h.mu,
	}
}

func (h *consoleHandler) WithGroup(name string) slog.Handler {
	if name == "" {
		return h
	}
	clone := &consoleHandler{
		writer: h.writer,
		level:  h.level,
		attrs:  append([]slog.Attr(nil), h.attrs...),
		group:  h.group,
		mu:     h.mu,
	}
	if clone.group == "" {
		clone.group = name
	} else {
		clone.group += "." + name
	}
	return clone
}

func appendConsoleAttr(
	attrs []slog.Attr,
	prefix string,
	attr slog.Attr,
) []slog.Attr {
	if attr.Equal(slog.Attr{}) {
		return attrs
	}
	attr.Value = attr.Value.Resolve()
	if attr.Value.Kind() == slog.KindGroup {
		group := prefix
		if attr.Key != "" {
			group = joinGroup(prefix, attr.Key)
		}
		for _, child := range attr.Value.Group() {
			attrs = appendConsoleAttr(attrs, group, child)
		}
		return attrs
	}
	attr.Key = joinGroup(prefix, attr.Key)
	return append(attrs, attr)
}

func joinGroup(prefix, key string) string {
	if prefix == "" {
		return key
	}
	if key == "" {
		return prefix
	}
	return prefix + "." + key
}

func encodeConsoleValue(value slog.Value) []byte {
	resolved := value.Resolve().Any()
	if errValue, ok := resolved.(error); ok {
		resolved = errValue.Error()
	}
	encoded, err := json.Marshal(resolved)
	if err == nil {
		return encoded
	}
	encoded, _ = json.Marshal(fmt.Sprint(resolved))
	return encoded
}

func consoleLevel(level slog.Level) string {
	if level >= slog.LevelError+4 {
		return "critical"
	}
	return strings.ToLower(level.String())
}
