package observability

import (
	"bytes"
	"context"
	"errors"
	"io"
	"log/slog"
	"strings"
	"testing"
	"time"
)

func TestConsoleHandlerKeepsVectorErrorSignal(t *testing.T) {
	var output bytes.Buffer
	handler := &consoleHandler{writer: &output, level: slog.LevelDebug}
	record := slog.NewRecord(time.Unix(0, 0), slog.LevelError, "Task failed", 0)
	record.AddAttrs(slog.String("task_id", "task-1"))
	if err := handler.Handle(context.Background(), record); err != nil {
		t.Fatal(err)
	}
	text := output.String()
	if !strings.Contains(text, "[error] Task failed") {
		t.Fatalf("missing Vector-compatible level/event: %s", text)
	}
	if !strings.Contains(text, "task_id=\"task-1\"") {
		t.Fatalf("missing structured context: %s", text)
	}
}

func TestLoggerConfiguration(t *testing.T) {
	for _, level := range []string{
		"",
		"debug",
		"INFO",
		"warning",
		"WARN",
		"ERROR",
		"critical",
	} {
		if _, err := NewLogger(level, "plain"); err != nil {
			t.Fatalf("NewLogger(%q, plain): %v", level, err)
		}
		if _, err := NewLogger(level, "json"); err != nil {
			t.Fatalf("NewLogger(%q, json): %v", level, err)
		}
	}
	if _, err := NewLogger("verbose", "plain"); err == nil {
		t.Fatal("expected unsupported level error")
	}
	if _, err := NewLogger("info", "xml"); err == nil {
		t.Fatal("expected unsupported format error")
	}
}

func TestConsoleHandlerAttributesGroupsAndLevels(t *testing.T) {
	var output bytes.Buffer
	base := &consoleHandler{writer: &output, level: slog.LevelInfo}
	if base.Enabled(context.Background(), slog.LevelDebug) {
		t.Fatal("debug should be disabled")
	}
	if !base.Enabled(context.Background(), slog.LevelError) {
		t.Fatal("error should be enabled")
	}
	handler := base.WithAttrs([]slog.Attr{
		slog.String("component", "test"),
		slog.Attr{},
	}).WithGroup("outer").WithGroup("inner")
	record := slog.NewRecord(time.Unix(0, 0), slog.LevelInfo, "event", 0)
	record.AddAttrs(slog.Any("unsupported", make(chan int)))
	if err := handler.Handle(context.Background(), record); err != nil {
		t.Fatal(err)
	}
	text := output.String()
	if !strings.Contains(text, `component="test"`) ||
		!strings.Contains(text, `outer.inner.unsupported="`) {
		t.Fatalf("unexpected console output: %s", text)
	}
}

func TestConsoleHandlerFormatsErrorsAndCriticalLevels(t *testing.T) {
	var output bytes.Buffer
	handler := &consoleHandler{writer: &output, level: slog.LevelDebug}
	record := slog.NewRecord(
		time.Unix(0, 0),
		slog.LevelError+4,
		"critical event",
		0,
	)
	record.AddAttrs(slog.Any("error", errors.New("boom")))
	if err := handler.Handle(context.Background(), record); err != nil {
		t.Fatal(err)
	}
	text := output.String()
	if !strings.Contains(text, `[critical] critical event`) ||
		!strings.Contains(text, `error="boom"`) {
		t.Fatalf("unexpected console output: %s", text)
	}
}

type failingWriter struct{}

func (failingWriter) Write([]byte) (int, error) {
	return 0, errors.New("write failed")
}

func TestConsoleHandlerPropagatesWriteErrors(t *testing.T) {
	handler := &consoleHandler{writer: failingWriter{}, level: slog.LevelDebug}
	record := slog.NewRecord(time.Now(), slog.LevelInfo, "event", 0)
	if err := handler.Handle(context.Background(), record); err == nil {
		t.Fatal("expected write error")
	}
	handler.writer = io.Discard
	record.AddAttrs(slog.String("key", "value"))
	if err := handler.Handle(context.Background(), record); err != nil {
		t.Fatal(err)
	}
}
