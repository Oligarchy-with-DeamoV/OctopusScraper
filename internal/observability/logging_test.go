package observability

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"syscall"
	"testing"
	"time"

	"go.uber.org/zap/zapcore"
)

func TestLoggerWritesStructuredJSONForVectorSignal(t *testing.T) {
	var output bytes.Buffer
	runtime, err := newLoggerRuntime(
		LoggerOptions{Level: "debug", Format: "plain"},
		zapcore.AddSync(&output),
	)
	if err != nil {
		t.Fatal(err)
	}
	runtime.Logger().Error(
		"Task failed",
		"task_id", "task-1",
		"items_processed", 7,
	)
	payload := decodeSingleLog(t, output.Bytes())
	if payload["level"] != "error" || payload["event"] != "Task failed" {
		t.Fatalf("missing Vector-compatible level/event: %#v", payload)
	}
	if payload["task_id"] != "task-1" ||
		payload["items_processed"] != float64(7) {
		t.Fatalf("missing business fields: %#v", payload)
	}
	if payload["timestamp"] == "" || payload["caller"] == "" {
		t.Fatalf("missing timestamp/caller: %#v", payload)
	}
	if !strings.Contains(payload["caller"].(string), "logging_test.go") {
		t.Fatalf("caller should point at slog call site: %#v", payload)
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
		for _, format := range []string{"", "plain", "json"} {
			runtime, err := newLoggerRuntime(
				LoggerOptions{Level: level, Format: format},
				zapcore.AddSync(io.Discard),
			)
			if err != nil {
				t.Fatalf("NewLoggerRuntime(%q, %q): %v", level, format, err)
			}
			if err := runtime.Close(); err != nil {
				t.Fatal(err)
			}
		}
	}
	if _, err := newLoggerRuntime(
		LoggerOptions{Level: "verbose"},
		zapcore.AddSync(io.Discard),
	); err == nil {
		t.Fatal("expected unsupported level error")
	}
	if _, err := NewLogger("verbose", "json"); err == nil {
		t.Fatal("expected compatibility constructor to reject unsupported level")
	}
	if _, err := newLoggerRuntime(
		LoggerOptions{Level: "info", Format: "xml"},
		zapcore.AddSync(io.Discard),
	); err == nil {
		t.Fatal("expected unsupported format error")
	}
	logger, err := NewLogger("debug", "plain")
	if err != nil {
		t.Fatal(err)
	}
	if !logger.Enabled(context.Background(), slog.LevelDebug) {
		t.Fatal("compatibility constructor should honor the requested level")
	}
}

func TestLoggerGroupsLevelsAndRedaction(t *testing.T) {
	var output bytes.Buffer
	runtime, err := newLoggerRuntime(
		LoggerOptions{Level: "info"},
		zapcore.AddSync(&output),
	)
	if err != nil {
		t.Fatal(err)
	}
	logger := runtime.Logger().
		With("component", "test").
		WithGroup("outer").
		WithGroup("inner")
	logger.Info(
		"event",
		"api_key", "secret",
		"database_url", "postgres://user:pass@db/app",
		"duration", time.Second,
		"enabled", true,
		"ratio", 1.5,
		"count", int64(-2),
		"size", uint64(3),
		"at", time.Unix(1, 0).UTC(),
	)
	payload := decodeSingleLog(t, output.Bytes())
	if payload["component"] != "test" ||
		payload["outer.inner.api_key"] != "[REDACTED]" ||
		payload["outer.inner.database_url"] != "[REDACTED]" ||
		payload["outer.inner.duration"] != float64(1) ||
		payload["outer.inner.enabled"] != true ||
		payload["outer.inner.ratio"] != 1.5 ||
		payload["outer.inner.count"] != float64(-2) ||
		payload["outer.inner.size"] != float64(3) ||
		payload["outer.inner.at"] == "" {
		t.Fatalf("unexpected structured output: %#v", payload)
	}
}

func TestSlogHandlerBranches(t *testing.T) {
	var output bytes.Buffer
	runtime, err := newLoggerRuntime(
		LoggerOptions{Level: "debug"},
		zapcore.AddSync(&output),
	)
	if err != nil {
		t.Fatal(err)
	}
	handler := runtime.Logger().Handler()
	if !handler.Enabled(context.Background(), slog.LevelWarn) {
		t.Fatal("warn should be enabled")
	}
	record := slog.NewRecord(time.Unix(0, 0), slog.LevelDebug, "no caller", 0)
	record.AddAttrs(slog.Group("", slog.String("child", "value")))
	if err := handler.Handle(context.Background(), record); err != nil {
		t.Fatal(err)
	}
	payload := decodeSingleLog(t, output.Bytes())
	if _, ok := payload["caller"]; ok {
		t.Fatalf("unexpected caller for zero PC: %#v", payload)
	}
	if payload["child"] != "value" {
		t.Fatalf("group without key was not flattened: %#v", payload)
	}

	levels := map[slog.Level]string{
		slog.LevelDebug:     "debug",
		slog.LevelInfo:      "info",
		slog.LevelWarn:      "warn",
		slog.LevelError:     "error",
		slog.LevelError + 4: "critical",
	}
	for level, want := range levels {
		if got := encodeLevel(slogLevelToZap(level)); got != want {
			t.Fatalf("level %s encoded as %q, want %q", level, got, want)
		}
	}
	if caller, ok := entryCaller(0); ok || caller.Defined {
		t.Fatalf("zero caller = %#v, %v", caller, ok)
	}
}

func TestLoggerWritesStdoutAndFileOnlyWhenConfigured(t *testing.T) {
	var stdout bytes.Buffer
	emptyLogPath := filepath.Join(t.TempDir(), "octopus.log")
	runtime, err := newLoggerRuntime(
		LoggerOptions{Level: "debug", RetentionDays: 3},
		zapcore.AddSync(&stdout),
	)
	if err != nil {
		t.Fatal(err)
	}
	runtime.Logger().Info("stdout only")
	if err := runtime.Close(); err != nil {
		t.Fatal(err)
	}
	if stdout.Len() == 0 {
		t.Fatal("stdout was not written")
	}
	if _, err := os.Stat(emptyLogPath); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("LOG_FILE empty should not create a file, stat error = %v", err)
	}

	logPath := filepath.Join(t.TempDir(), "octopus.log")
	stdout.Reset()
	runtime, err = newLoggerRuntime(
		LoggerOptions{
			Level:         "debug",
			FilePath:      logPath,
			RetentionDays: 3,
		},
		zapcore.AddSync(&stdout),
	)
	if err != nil {
		t.Fatal(err)
	}
	runtime.Logger().Info("dual write", "business", "field")
	if err := runtime.Close(); err != nil {
		t.Fatal(err)
	}
	if stdout.Len() == 0 {
		t.Fatal("stdout was not written")
	}
	fileBytes, err := os.ReadFile(logPath)
	if err != nil {
		t.Fatal(err)
	}
	stdoutPayload := decodeSingleLog(t, stdout.Bytes())
	filePayload := decodeSingleLog(t, fileBytes)
	if stdoutPayload["event"] != filePayload["event"] ||
		filePayload["business"] != "field" {
		t.Fatalf("file/stdout payload mismatch: stdout=%#v file=%#v", stdoutPayload, filePayload)
	}
}

func TestLoggerLevelFilteringAndConcurrentUpdates(t *testing.T) {
	var output lockedBuffer
	runtime, err := newLoggerRuntime(
		LoggerOptions{Level: "error"},
		zapcore.AddSync(&output),
	)
	if err != nil {
		t.Fatal(err)
	}
	logger := runtime.Logger()
	logger.Info("filtered")
	if output.Len() != 0 {
		t.Fatalf("info should be filtered: %s", output.String())
	}
	if err := runtime.SetLevel("debug"); err != nil {
		t.Fatal(err)
	}
	if runtime.Level() != "debug" {
		t.Fatalf("runtime level = %q", runtime.Level())
	}
	logger.Debug("visible")
	if !strings.Contains(output.String(), `"event":"visible"`) {
		t.Fatalf("debug log missing after level update: %s", output.String())
	}

	var wg sync.WaitGroup
	for worker := 0; worker < 8; worker++ {
		wg.Add(1)
		go func(worker int) {
			defer wg.Done()
			for index := 0; index < 50; index++ {
				if index%2 == 0 {
					_ = runtime.SetLevel("debug")
				} else {
					_ = runtime.SetLevel("error")
				}
				logger.Info("concurrent level check", "worker", worker)
			}
		}(worker)
	}
	wg.Wait()
	if err := runtime.SetLevel("invalid"); err == nil {
		t.Fatal("expected invalid dynamic level error")
	}
}

func TestDailyRotationAndLumberjackConfiguration(t *testing.T) {
	var now = time.Date(2026, 8, 19, 10, 0, 0, 0, time.UTC)
	fake := &fakeRotatingSink{}
	sink := newDailyRotatingSink(fake, func() time.Time { return now })
	if _, err := sink.Write([]byte("first")); err != nil {
		t.Fatal(err)
	}
	now = now.Add(10 * time.Hour)
	if _, err := sink.Write([]byte("same-day")); err != nil {
		t.Fatal(err)
	}
	if fake.rotations != 0 {
		t.Fatalf("rotated before date boundary: %d", fake.rotations)
	}
	now = now.Add(6 * time.Hour)
	if _, err := sink.Write([]byte("next-day")); err != nil {
		t.Fatal(err)
	}
	if fake.rotations != 1 {
		t.Fatalf("date rotation count = %d", fake.rotations)
	}

	logPath := filepath.Join(t.TempDir(), "octopus.log")
	fileSink, err := newLogFileSink(logPath, 9, time.Now)
	if err != nil {
		t.Fatal(err)
	}
	logger, ok := fileSink.sink.(*lumberjackLogger)
	if !ok {
		t.Fatalf("unexpected file sink type %T", fileSink.sink)
	}
	if logger.MaxSize != LogFileMaxSizeMB ||
		logger.MaxAge != 9 ||
		!logger.Compress ||
		!logger.LocalTime ||
		logger.Filename != logPath {
		t.Fatalf("lumberjack config = %#v", logger)
	}
	blockingParent := filepath.Join(t.TempDir(), "file-parent")
	if err := os.WriteFile(blockingParent, []byte("blocked"), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := newLogFileSink(filepath.Join(blockingParent, "octopus.log"), 1, time.Now); err == nil {
		t.Fatal("expected log directory creation to fail")
	}

	rotateErr := errors.New("rotate failed")
	failing := &fakeRotatingSink{rotateErr: rotateErr}
	now = time.Date(2026, 8, 19, 23, 0, 0, 0, time.UTC)
	sink = newDailyRotatingSink(failing, func() time.Time { return now })
	if _, err := sink.Write([]byte("first")); err != nil {
		t.Fatal(err)
	}
	now = now.Add(2 * time.Hour)
	if _, err := sink.Write([]byte("next")); !errors.Is(err, rotateErr) {
		t.Fatalf("rotation error = %v", err)
	}

	defaultClockSink := newDailyRotatingSink(&fakeRotatingSink{}, nil)
	if _, err := defaultClockSink.Write([]byte("uses time.Now")); err != nil {
		t.Fatal(err)
	}
}

func TestRetentionDaysAreBounded(t *testing.T) {
	tests := []struct {
		value int
		want  int
	}{
		{0, DefaultLogRetentionDays},
		{1, 1},
		{MaxLogRetentionDays + 10, MaxLogRetentionDays},
	}
	for _, test := range tests {
		got, err := normalizeRetentionDays(test.value)
		if err != nil {
			t.Fatal(err)
		}
		if got != test.want {
			t.Fatalf("normalizeRetentionDays(%d) = %d, want %d", test.value, got, test.want)
		}
	}
	if _, err := normalizeRetentionDays(-1); err == nil {
		t.Fatal("expected negative retention to fail")
	}
}

func TestCloseFlushesBenignStdoutAndPropagatesRealSinkErrors(t *testing.T) {
	stdout := &syncErrorWriter{err: syscall.EINVAL}
	if err := (&benignStdoutSyncer{WriteSyncer: &syncErrorWriter{err: errors.New("real stdout sync")}}).Sync(); err == nil {
		t.Fatal("expected non-benign stdout sync error")
	}
	runtime, err := newLoggerRuntime(
		LoggerOptions{Level: "info"},
		&benignStdoutSyncer{WriteSyncer: stdout},
	)
	if err != nil {
		t.Fatal(err)
	}

	if err := runtime.Close(); err != nil {
		t.Fatalf("benign stdout sync error should be ignored: %v", err)
	}

	realErr := errors.New("disk unavailable")
	runtime, err = newLoggerRuntime(
		LoggerOptions{Level: "info"},
		&syncErrorWriter{err: realErr},
	)
	if err != nil {
		t.Fatal(err)
	}
	if err := runtime.Close(); !errors.Is(err, realErr) {
		t.Fatalf("real sync error = %v", err)
	}

	closeErr := errors.New("close failed")
	runtime = &LoggerRuntime{
		core:   zapcore.NewNopCore(),
		closer: closeErrorCloser{err: closeErr},
	}
	if err := runtime.Close(); !errors.Is(err, closeErr) {
		t.Fatalf("close error = %v", err)
	}
}

func TestSlogFieldConversionBranches(t *testing.T) {
	if fields := slogAttrToZapFields("", slog.Attr{}); fields != nil {
		t.Fatalf("empty attr fields = %#v", fields)
	}
	if fields := slogAttrToZapFields("", slog.String("", "value")); fields != nil {
		t.Fatalf("empty key fields = %#v", fields)
	}
	for _, key := range []string{"password", "client-secret", "mcp-token", "db_url"} {
		fields := slogAttrToZapFields("", slog.String(key, "secret"))
		if len(fields) != 1 {
			t.Fatalf("%s fields = %#v", key, fields)
		}
	}
	errFields := slogAttrToZapFields("", slog.Any("error", errors.New("boom")))
	anyFields := slogAttrToZapFields("", slog.Any("payload", map[string]string{"k": "v"}))
	logValuerFields := slogAttrToZapFields("", slog.Any("value", slog.StringValue("valuer")))
	if len(errFields) != 1 || len(anyFields) != 1 || len(logValuerFields) != 1 {
		t.Fatalf("field conversion lengths = %d/%d/%d", len(errFields), len(anyFields), len(logValuerFields))
	}
}

func TestCriticalLevelMatchesVectorFilter(t *testing.T) {
	var output bytes.Buffer
	runtime, err := newLoggerRuntime(
		LoggerOptions{Level: "critical"},
		zapcore.AddSync(&output),
	)
	if err != nil {
		t.Fatal(err)
	}
	logger := runtime.Logger()
	logger.Error("filtered error")
	if output.Len() != 0 {
		t.Fatalf("error should be filtered at critical level: %s", output.String())
	}
	logger.Log(context.Background(), slog.LevelError+4, "Task failed")
	payload := decodeSingleLog(t, output.Bytes())
	if payload["level"] != "critical" || payload["event"] != "Task failed" {
		t.Fatalf("critical vector payload = %#v", payload)
	}
}

func decodeSingleLog(t *testing.T, data []byte) map[string]any {
	t.Helper()
	lines := bytes.Split(bytes.TrimSpace(data), []byte("\n"))
	if len(lines) != 1 {
		t.Fatalf("expected one log line, got %d: %s", len(lines), data)
	}
	var payload map[string]any
	if err := json.Unmarshal(lines[0], &payload); err != nil {
		_, file, line, _ := runtime.Caller(1)
		t.Fatalf("%s:%d invalid JSON log %q: %v", file, line, string(lines[0]), err)
	}
	return payload
}

type lockedBuffer struct {
	mu sync.Mutex
	bytes.Buffer
}

func (b *lockedBuffer) Write(payload []byte) (int, error) {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.Buffer.Write(payload)
}

func (b *lockedBuffer) Len() int {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.Buffer.Len()
}

func (b *lockedBuffer) String() string {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.Buffer.String()
}

type fakeRotatingSink struct {
	rotations int
	closed    bool
	rotateErr error
}

func (s *fakeRotatingSink) Write(payload []byte) (int, error) {
	return len(payload), nil
}

func (s *fakeRotatingSink) Rotate() error {
	if s.rotateErr != nil {
		return s.rotateErr
	}
	s.rotations++
	return nil
}

func (s *fakeRotatingSink) Close() error {
	s.closed = true
	return nil
}

type syncErrorWriter struct {
	err error
}

func (w *syncErrorWriter) Write(payload []byte) (int, error) {
	return len(payload), nil
}

func (w *syncErrorWriter) Sync() error {
	return w.err
}

type closeErrorCloser struct {
	err error
}

func (c closeErrorCloser) Close() error {
	return c.err
}
