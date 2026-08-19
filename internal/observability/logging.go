package observability

import (
	"context"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"syscall"
	"time"

	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
	"gopkg.in/natefinch/lumberjack.v2"
)

const (
	DefaultLogRetentionDays = 14
	MaxLogRetentionDays     = 365
	LogFileMaxSizeMB        = 100
)

type LoggerOptions struct {
	Level         string
	Format        string
	FilePath      string
	RetentionDays int
}

type LoggerRuntime struct {
	logger *slog.Logger
	core   zapcore.Core
	level  zap.AtomicLevel
	closer io.Closer
}

func NewLoggerRuntime(options LoggerOptions) (*LoggerRuntime, error) {
	return newLoggerRuntime(options, zapcore.Lock(&benignStdoutSyncer{
		WriteSyncer: zapcore.AddSync(os.Stdout),
	}))
}

func NewLogger(levelText, format string) (*slog.Logger, error) {
	runtime, err := NewLoggerRuntime(LoggerOptions{
		Level:         levelText,
		Format:        format,
		RetentionDays: DefaultLogRetentionDays,
	})
	if err != nil {
		return nil, err
	}
	return runtime.Logger(), nil
}

func (r *LoggerRuntime) Logger() *slog.Logger {
	return r.logger
}

func (r *LoggerRuntime) SetLevel(levelText string) error {
	level, err := parseZapLevel(levelText)
	if err != nil {
		return err
	}
	r.level.SetLevel(level)
	return nil
}

func (r *LoggerRuntime) Level() string {
	return encodeLevel(r.level.Level())
}

func (r *LoggerRuntime) Close() error {
	var closeErrors []error
	if r.core != nil {
		if err := r.core.Sync(); err != nil {
			closeErrors = append(closeErrors, fmt.Errorf("sync logger: %w", err))
		}
	}
	if r.closer != nil {
		if err := r.closer.Close(); err != nil {
			closeErrors = append(closeErrors, fmt.Errorf("close log file: %w", err))
		}
	}
	return errors.Join(closeErrors...)
}

func newLoggerRuntime(
	options LoggerOptions,
	stdout zapcore.WriteSyncer,
) (*LoggerRuntime, error) {
	if err := validateLogFormat(options.Format); err != nil {
		return nil, err
	}
	initialLevel, err := parseZapLevel(options.Level)
	if err != nil {
		return nil, err
	}
	retentionDays, err := normalizeRetentionDays(options.RetentionDays)
	if err != nil {
		return nil, err
	}
	level := zap.NewAtomicLevelAt(initialLevel)
	sink := stdout
	var closer io.Closer
	if filePath := strings.TrimSpace(options.FilePath); filePath != "" {
		fileSink, err := newLogFileSink(filePath, retentionDays, time.Now)
		if err != nil {
			return nil, err
		}
		closer = fileSink
		sink = zapcore.NewMultiWriteSyncer(stdout, zapcore.Lock(fileSink))
	}
	core := zapcore.NewCore(jsonEncoder(), sink, level)
	handler := &zapSlogHandler{core: core}
	return &LoggerRuntime{
		logger: slog.New(handler),
		core:   core,
		level:  level,
		closer: closer,
	}, nil
}

func validateLogFormat(format string) error {
	switch strings.ToLower(strings.TrimSpace(format)) {
	case "", "json", "plain":
		return nil
	default:
		return fmt.Errorf("unsupported log format: %s", format)
	}
}

func parseZapLevel(value string) (zapcore.Level, error) {
	switch strings.ToUpper(strings.TrimSpace(value)) {
	case "DEBUG":
		return zapcore.DebugLevel, nil
	case "INFO", "":
		return zapcore.InfoLevel, nil
	case "WARNING", "WARN":
		return zapcore.WarnLevel, nil
	case "ERROR":
		return zapcore.ErrorLevel, nil
	case "CRITICAL":
		return zapcore.DPanicLevel, nil
	default:
		return zapcore.InfoLevel, fmt.Errorf("unsupported log level: %s", value)
	}
}

func normalizeRetentionDays(value int) (int, error) {
	if value == 0 {
		return DefaultLogRetentionDays, nil
	}
	if value < 0 {
		return 0, errors.New("LOG_RETENTION_DAYS must be zero or greater")
	}
	if value > MaxLogRetentionDays {
		return MaxLogRetentionDays, nil
	}
	return value, nil
}

func jsonEncoder() zapcore.Encoder {
	config := zapcore.EncoderConfig{
		TimeKey:        "timestamp",
		LevelKey:       "level",
		NameKey:        "",
		CallerKey:      "caller",
		FunctionKey:    "",
		MessageKey:     "event",
		StacktraceKey:  "",
		LineEnding:     zapcore.DefaultLineEnding,
		EncodeLevel:    encodeZapLevel,
		EncodeTime:     zapcore.RFC3339NanoTimeEncoder,
		EncodeDuration: zapcore.SecondsDurationEncoder,
		EncodeCaller:   zapcore.ShortCallerEncoder,
	}
	return zapcore.NewJSONEncoder(config)
}

func encodeZapLevel(level zapcore.Level, encoder zapcore.PrimitiveArrayEncoder) {
	encoder.AppendString(encodeLevel(level))
}

func encodeLevel(level zapcore.Level) string {
	if level >= zapcore.DPanicLevel {
		return "critical"
	}
	return level.String()
}

type zapSlogHandler struct {
	core  zapcore.Core
	attrs []zap.Field
	group string
}

func (h *zapSlogHandler) Enabled(_ context.Context, level slog.Level) bool {
	return h.core.Enabled(slogLevelToZap(level))
}

func (h *zapSlogHandler) Handle(_ context.Context, record slog.Record) error {
	level := slogLevelToZap(record.Level)
	if !h.core.Enabled(level) {
		return nil
	}
	fields := append([]zap.Field(nil), h.attrs...)
	record.Attrs(func(attr slog.Attr) bool {
		fields = append(fields, slogAttrToZapFields(h.group, attr)...)
		return true
	})
	entry := zapcore.Entry{
		Level:   level,
		Time:    record.Time,
		Message: record.Message,
	}
	if caller, ok := entryCaller(record.PC); ok {
		entry.Caller = caller
	}
	return h.core.Write(entry, fields)
}

func (h *zapSlogHandler) WithAttrs(attrs []slog.Attr) slog.Handler {
	fields := append([]zap.Field(nil), h.attrs...)
	for _, attr := range attrs {
		fields = append(fields, slogAttrToZapFields(h.group, attr)...)
	}
	return &zapSlogHandler{
		core:  h.core,
		attrs: fields,
		group: h.group,
	}
}

func (h *zapSlogHandler) WithGroup(name string) slog.Handler {
	if name == "" {
		return h
	}
	group := name
	if h.group != "" {
		group = h.group + "." + name
	}
	return &zapSlogHandler{
		core:  h.core,
		attrs: append([]zap.Field(nil), h.attrs...),
		group: group,
	}
}

func slogLevelToZap(level slog.Level) zapcore.Level {
	if level >= slog.LevelError+4 {
		return zapcore.DPanicLevel
	}
	switch {
	case level >= slog.LevelError:
		return zapcore.ErrorLevel
	case level >= slog.LevelWarn:
		return zapcore.WarnLevel
	case level >= slog.LevelInfo:
		return zapcore.InfoLevel
	default:
		return zapcore.DebugLevel
	}
}

func entryCaller(programCounter uintptr) (zapcore.EntryCaller, bool) {
	if programCounter == 0 {
		return zapcore.EntryCaller{}, false
	}
	frame, _ := runtime.CallersFrames([]uintptr{programCounter}).Next()
	if frame.File == "" {
		return zapcore.EntryCaller{}, false
	}
	return zapcore.EntryCaller{
		Defined:  true,
		PC:       programCounter,
		File:     frame.File,
		Line:     frame.Line,
		Function: frame.Function,
	}, true
}

func slogAttrToZapFields(prefix string, attr slog.Attr) []zap.Field {
	if isEmptySlogAttr(attr) {
		return nil
	}
	attr.Value = attr.Value.Resolve()
	if attr.Value.Kind() == slog.KindGroup {
		group := prefix
		if attr.Key != "" {
			group = joinGroup(prefix, attr.Key)
		}
		var fields []zap.Field
		for _, child := range attr.Value.Group() {
			fields = append(fields, slogAttrToZapFields(group, child)...)
		}
		return fields
	}
	key := joinGroup(prefix, attr.Key)
	if key == "" {
		return nil
	}
	if shouldRedactLogField(key) {
		return []zap.Field{zap.String(key, "[REDACTED]")}
	}
	switch attr.Value.Kind() {
	case slog.KindString:
		return []zap.Field{zap.String(key, attr.Value.String())}
	case slog.KindBool:
		return []zap.Field{zap.Bool(key, attr.Value.Bool())}
	case slog.KindDuration:
		return []zap.Field{zap.Duration(key, attr.Value.Duration())}
	case slog.KindFloat64:
		return []zap.Field{zap.Float64(key, attr.Value.Float64())}
	case slog.KindInt64:
		return []zap.Field{zap.Int64(key, attr.Value.Int64())}
	case slog.KindTime:
		return []zap.Field{zap.Time(key, attr.Value.Time())}
	case slog.KindUint64:
		return []zap.Field{zap.Uint64(key, attr.Value.Uint64())}
	case slog.KindAny:
		if err, ok := attr.Value.Any().(error); ok {
			return []zap.Field{zap.NamedError(key, err)}
		}
		return []zap.Field{zap.Any(key, attr.Value.Any())}
	default:
		return []zap.Field{zap.String(key, attr.Value.String())}
	}
}

func isEmptySlogAttr(attr slog.Attr) bool {
	return attr.Key == "" &&
		attr.Value.Kind() == slog.KindAny &&
		attr.Value.Any() == nil
}

func shouldRedactLogField(key string) bool {
	normalized := strings.ToLower(strings.ReplaceAll(key, "-", "_"))
	switch {
	case strings.Contains(normalized, "api_key"):
		return true
	case strings.Contains(normalized, "password"):
		return true
	case strings.Contains(normalized, "secret"):
		return true
	case strings.Contains(normalized, "token"):
		return true
	case strings.Contains(normalized, "database_url"):
		return true
	case strings.Contains(normalized, "db_url"):
		return true
	default:
		return false
	}
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

type benignStdoutSyncer struct {
	zapcore.WriteSyncer
}

func (s *benignStdoutSyncer) Sync() error {
	err := s.WriteSyncer.Sync()
	if isBenignStdoutSyncError(err) {
		return nil
	}
	return err
}

func isBenignStdoutSyncError(err error) bool {
	return errors.Is(err, syscall.EINVAL) ||
		errors.Is(err, syscall.ENOTTY)
}

type rotateWriteCloser interface {
	io.WriteCloser
	Rotate() error
}

type lumberjackLogger = lumberjack.Logger

type dailyRotatingSink struct {
	sink rotateWriteCloser
	now  func() time.Time

	mu  sync.Mutex
	day string
}

func newLogFileSink(
	path string,
	retentionDays int,
	now func() time.Time,
) (*dailyRotatingSink, error) {
	if parent := filepath.Dir(path); parent != "." && parent != "" {
		if err := os.MkdirAll(parent, 0o755); err != nil {
			return nil, fmt.Errorf("create log directory: %w", err)
		}
	}
	return newDailyRotatingSink(&lumberjack.Logger{
		Filename:   path,
		MaxSize:    LogFileMaxSizeMB,
		MaxAge:     retentionDays,
		MaxBackups: 0,
		LocalTime:  true,
		Compress:   true,
	}, now), nil
}

func newDailyRotatingSink(
	sink rotateWriteCloser,
	now func() time.Time,
) *dailyRotatingSink {
	if now == nil {
		now = time.Now
	}
	return &dailyRotatingSink{sink: sink, now: now}
}

func (s *dailyRotatingSink) Write(payload []byte) (int, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	day := s.now().Format("2006-01-02")
	if s.day == "" {
		s.day = day
	} else if s.day != day {
		if err := s.sink.Rotate(); err != nil {
			return 0, err
		}
		s.day = day
	}
	return s.sink.Write(payload)
}

func (s *dailyRotatingSink) Sync() error {
	return nil
}

func (s *dailyRotatingSink) Close() error {
	return s.sink.Close()
}
