package mcpapi

import (
	"context"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/config"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/storage"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

const (
	defaultListLimit = 20
	maxListLimit     = 50
	defaultMaxChars  = 20000
	maxContentChars  = 50000
	maxRequestBytes  = 1 << 20
	listContentsTool = "list_contents"
	getContentTool   = "get_content"
	successResult    = "success"
	errorResult      = "error"
	notFoundResult   = "not_found"
)

var errContentNotFound = errors.New("content_id not found")

type service struct {
	reader   storage.ContentReader
	logger   *slog.Logger
	cfg      config.MCPConfig
	shutdown context.Context
}

type listContentsInput struct {
	Limit           int      `json:"limit,omitempty"`
	Cursor          string   `json:"cursor,omitempty"`
	ScraperName     string   `json:"scraper_name,omitempty"`
	Tags            []string `json:"tags,omitempty"`
	CollectedAfter  string   `json:"collected_after,omitempty"`
	CollectedBefore string   `json:"collected_before,omitempty"`
}

type contentMetadataOutput struct {
	ContentID   string   `json:"content_id"`
	Title       string   `json:"title"`
	Link        string   `json:"link"`
	Summary     string   `json:"summary"`
	Published   string   `json:"published"`
	Author      *string  `json:"author,omitempty"`
	Keywords    []string `json:"keywords"`
	Tags        []string `json:"tags"`
	ScraperName *string  `json:"scraper_name,omitempty"`
	CollectedAt string   `json:"collected_at"`
}

type listContentsOutput struct {
	Contents   []contentMetadataOutput `json:"contents"`
	NextCursor string                  `json:"next_cursor,omitempty"`
}

type getContentInput struct {
	ContentID string `json:"content_id"`
	Offset    int    `json:"offset,omitempty"`
	MaxChars  int    `json:"max_chars,omitempty"`
}

type getContentOutput struct {
	ContentID   string   `json:"content_id"`
	Title       string   `json:"title"`
	Link        string   `json:"link"`
	Summary     string   `json:"summary"`
	Content     string   `json:"content"`
	Published   string   `json:"published"`
	Author      *string  `json:"author,omitempty"`
	Keywords    []string `json:"keywords"`
	Tags        []string `json:"tags"`
	ScraperName *string  `json:"scraper_name,omitempty"`
	CollectedAt string   `json:"collected_at"`
	NextOffset  int      `json:"next_offset"`
	Truncated   bool     `json:"truncated"`
}

type cursorPayload struct {
	CreatedAt string `json:"created_at"`
	ContentID string `json:"content_id"`
}

// NewHandler builds the optional stateless MCP HTTP endpoint.
func NewHandler(
	shutdown context.Context,
	logger *slog.Logger,
	reader storage.ContentReader,
	cfg config.MCPConfig,
	version string,
) http.Handler {
	svc := &service{
		reader:   reader,
		logger:   logger,
		cfg:      cfg,
		shutdown: shutdown,
	}
	discardLogger := slog.New(slog.NewTextHandler(io.Discard, nil))
	streamable := mcp.NewStreamableHTTPHandler(func(*http.Request) *mcp.Server {
		server := mcp.NewServer(
			&mcp.Implementation{Name: "octopus-scraper", Version: version},
			&mcp.ServerOptions{
				Capabilities: &mcp.ServerCapabilities{},
				Logger:       discardLogger,
			},
		)
		svc.addTools(server)
		return server
	}, &mcp.StreamableHTTPOptions{
		Stateless:                    true,
		JSONResponse:                 true,
		Logger:                       discardLogger,
		MaxRequestBodyBytes:          maxRequestBytes,
		PropagateRequestCancellation: true,
	})
	return rejectOrigin(authorize(cfg.APIToken, limitConcurrency(cfg.MaxConcurrentQueries, streamable)))
}

func (s *service) addTools(server *mcp.Server) {
	annotations := &mcp.ToolAnnotations{
		ReadOnlyHint: true,
		Title:        "Read canonical OctopusScraper content",
	}
	mcp.AddTool(server, &mcp.Tool{
		Name:        listContentsTool,
		Title:       "List contents",
		Description: "List canonical PostgreSQL content metadata using bounded filters and keyset pagination.",
		Annotations: annotations,
	}, s.listContents)
	mcp.AddTool(server, &mcp.Tool{
		Name:        getContentTool,
		Title:       "Get content",
		Description: "Read one canonical PostgreSQL content record by content_id with Unicode-safe chunking.",
		Annotations: annotations,
	}, s.getContent)
}

func (s *service) listContents(ctx context.Context, _ *mcp.CallToolRequest, input listContentsInput) (_ *mcp.CallToolResult, output listContentsOutput, err error) {
	started := time.Now()
	result := errorResult
	defer func() {
		if err == nil {
			result = successResult
		}
		s.logTool(listContentsTool, started, result)
	}()
	opts, err := parseListOptions(input)
	if err != nil {
		return nil, listContentsOutput{}, err
	}
	queryCtx, cancel := s.queryContext(ctx)
	defer cancel()
	page, err := s.reader.ListContents(queryCtx, opts)
	if err != nil {
		return nil, listContentsOutput{}, err
	}
	output.Contents = make([]contentMetadataOutput, 0, len(page.Items))
	for _, item := range page.Items {
		output.Contents = append(output.Contents, metadataOutput(item))
	}
	if page.NextCursor != nil {
		output.NextCursor = encodeCursor(*page.NextCursor)
	}
	return nil, output, nil
}

func (s *service) getContent(ctx context.Context, _ *mcp.CallToolRequest, input getContentInput) (_ *mcp.CallToolResult, output getContentOutput, err error) {
	started := time.Now()
	result := errorResult
	defer func() {
		if errors.Is(err, errContentNotFound) {
			result = notFoundResult
		} else if err == nil {
			result = successResult
		}
		s.logTool(getContentTool, started, result)
	}()
	contentID := strings.TrimSpace(input.ContentID)
	if contentID == "" {
		return nil, getContentOutput{}, errors.New("content_id is required")
	}
	offset := input.Offset
	if offset < 0 {
		return nil, getContentOutput{}, errors.New("offset must be zero or greater")
	}
	maxChars := input.MaxChars
	if maxChars == 0 {
		maxChars = defaultMaxChars
	}
	if maxChars < 1 || maxChars > maxContentChars {
		return nil, getContentOutput{}, fmt.Errorf("max_chars must be between 1 and %d", maxContentChars)
	}
	queryCtx, cancel := s.queryContext(ctx)
	defer cancel()
	record, ok, err := s.reader.GetContent(queryCtx, contentID)
	if err != nil {
		return nil, getContentOutput{}, err
	}
	if !ok {
		return nil, getContentOutput{}, fmt.Errorf("%w: %s", errContentNotFound, contentID)
	}
	output = contentOutput(record)
	output.Content, output.NextOffset, output.Truncated = sliceRunes(record.Content, offset, maxChars)
	return nil, output, nil
}

func (s *service) queryContext(parent context.Context) (context.Context, context.CancelFunc) {
	timeout := s.cfg.QueryTimeout
	if timeout <= 0 {
		timeout = 5 * time.Second
	}
	ctx, cancel := context.WithTimeout(parent, timeout)
	stop := context.AfterFunc(s.shutdown, cancel)
	return ctx, func() {
		stop()
		cancel()
	}
}

func (s *service) logTool(tool string, started time.Time, result string) {
	if s.logger == nil {
		return
	}
	s.logger.Info(
		"MCP tool completed",
		"tool", tool,
		"duration_ms", time.Since(started).Seconds()*1000,
		"result", result,
	)
}

func parseListOptions(input listContentsInput) (storage.ContentListOptions, error) {
	limit := input.Limit
	if limit == 0 {
		limit = defaultListLimit
	}
	if limit < 1 || limit > maxListLimit {
		return storage.ContentListOptions{}, fmt.Errorf("limit must be between 1 and %d", maxListLimit)
	}
	var cursor *storage.ContentListCursor
	if strings.TrimSpace(input.Cursor) != "" {
		parsed, err := decodeCursor(input.Cursor)
		if err != nil {
			return storage.ContentListOptions{}, err
		}
		cursor = &parsed
	}
	var collectedAfter *time.Time
	if strings.TrimSpace(input.CollectedAfter) != "" {
		parsed, err := time.Parse(time.RFC3339, input.CollectedAfter)
		if err != nil {
			return storage.ContentListOptions{}, fmt.Errorf("collected_after must be RFC3339: %w", err)
		}
		collectedAfter = &parsed
	}
	var collectedBefore *time.Time
	if strings.TrimSpace(input.CollectedBefore) != "" {
		parsed, err := time.Parse(time.RFC3339, input.CollectedBefore)
		if err != nil {
			return storage.ContentListOptions{}, fmt.Errorf("collected_before must be RFC3339: %w", err)
		}
		collectedBefore = &parsed
	}
	if collectedAfter != nil && collectedBefore != nil && collectedAfter.After(*collectedBefore) {
		return storage.ContentListOptions{}, errors.New("collected_after must be before or equal to collected_before")
	}
	return storage.ContentListOptions{
		Limit:           limit,
		Cursor:          cursor,
		ScraperName:     strings.TrimSpace(input.ScraperName),
		Tags:            compactStrings(input.Tags),
		CollectedAfter:  collectedAfter,
		CollectedBefore: collectedBefore,
	}, nil
}

func metadataOutput(item storage.ContentMetadata) contentMetadataOutput {
	return contentMetadataOutput{
		ContentID:   item.ContentID,
		Title:       item.Title,
		Link:        item.Link,
		Summary:     item.Summary,
		Published:   item.Published,
		Author:      item.Author,
		Keywords:    nonNilStrings(item.Keywords),
		Tags:        nonNilStrings(item.Tags),
		ScraperName: item.ScraperName,
		CollectedAt: item.CollectedAt.Format(time.RFC3339Nano),
	}
}

func contentOutput(record storage.ContentRecord) getContentOutput {
	metadata := metadataOutput(record.ContentMetadata)
	return getContentOutput{
		ContentID:   metadata.ContentID,
		Title:       metadata.Title,
		Link:        metadata.Link,
		Summary:     metadata.Summary,
		Published:   metadata.Published,
		Author:      metadata.Author,
		Keywords:    metadata.Keywords,
		Tags:        metadata.Tags,
		ScraperName: metadata.ScraperName,
		CollectedAt: metadata.CollectedAt,
	}
}

func encodeCursor(cursor storage.ContentListCursor) string {
	payload := cursorPayload{
		CreatedAt: cursor.CreatedAt.Format(time.RFC3339Nano),
		ContentID: cursor.ContentID,
	}
	encoded, _ := json.Marshal(payload)
	return base64.RawURLEncoding.EncodeToString(encoded)
}

func decodeCursor(raw string) (storage.ContentListCursor, error) {
	decoded, err := base64.RawURLEncoding.DecodeString(raw)
	if err != nil {
		return storage.ContentListCursor{}, fmt.Errorf("cursor is invalid: %w", err)
	}
	decoder := json.NewDecoder(strings.NewReader(string(decoded)))
	decoder.DisallowUnknownFields()
	var payload cursorPayload
	if err := decoder.Decode(&payload); err != nil {
		return storage.ContentListCursor{}, fmt.Errorf("cursor is invalid: %w", err)
	}
	createdAt, err := time.Parse(time.RFC3339Nano, payload.CreatedAt)
	if err != nil {
		return storage.ContentListCursor{}, fmt.Errorf("cursor is invalid: %w", err)
	}
	if payload.ContentID == "" {
		return storage.ContentListCursor{}, errors.New("cursor is invalid: missing content_id")
	}
	return storage.ContentListCursor{CreatedAt: createdAt, ContentID: payload.ContentID}, nil
}

func compactStrings(values []string) []string {
	output := make([]string, 0, len(values))
	seen := make(map[string]struct{}, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, ok := seen[value]; ok {
			continue
		}
		seen[value] = struct{}{}
		output = append(output, value)
	}
	return output
}

func nonNilStrings(values []string) []string {
	if values == nil {
		return []string{}
	}
	return values
}

func sliceRunes(value string, offset, maxChars int) (string, int, bool) {
	runes := []rune(value)
	if offset >= len(runes) {
		return "", len(runes), false
	}
	end := offset + maxChars
	if end > len(runes) {
		end = len(runes)
	}
	return string(runes[offset:end]), end, end < len(runes)
}

func rejectOrigin(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Origin") != "" {
			http.Error(w, http.StatusText(http.StatusForbidden), http.StatusForbidden)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func authorize(token string, next http.Handler) http.Handler {
	expected := sha256.Sum256([]byte(token))
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		const prefix = "Bearer "
		header := r.Header.Get("Authorization")
		if !strings.HasPrefix(header, prefix) {
			http.Error(w, http.StatusText(http.StatusUnauthorized), http.StatusUnauthorized)
			return
		}
		actual := sha256.Sum256([]byte(strings.TrimSpace(strings.TrimPrefix(header, prefix))))
		if subtle.ConstantTimeCompare(actual[:], expected[:]) != 1 {
			http.Error(w, http.StatusText(http.StatusUnauthorized), http.StatusUnauthorized)
			return
		}
		next.ServeHTTP(w, r)
	})
}

func limitConcurrency(limit int, next http.Handler) http.Handler {
	if limit <= 0 {
		limit = 1
	}
	sem := make(chan struct{}, limit)
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		select {
		case sem <- struct{}{}:
			defer func() { <-sem }()
			next.ServeHTTP(w, r)
		default:
			http.Error(w, http.StatusText(http.StatusTooManyRequests), http.StatusTooManyRequests)
		}
	})
}
