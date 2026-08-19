package processor

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
)

const (
	maxLLMResponseBytes  = 4 << 20
	maxLLMErrorBodyBytes = 2048
)

type ChatMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type ChatRequest struct {
	BaseURL        string
	APIKey         string
	Model          string
	Messages       []ChatMessage
	Temperature    float64
	MaxTokens      int
	ResponseFormat string
}

type OpenAICompatibleClient struct {
	httpClient *http.Client
	cfg        BaseLLMProcessorConfig
}

func NewOpenAICompatibleClient(httpClient *http.Client, cfg BaseLLMProcessorConfig) *OpenAICompatibleClient {
	if httpClient == nil {
		httpClient = &http.Client{}
	}
	return &OpenAICompatibleClient{httpClient: httpClient, cfg: cfg}
}

func (c *OpenAICompatibleClient) CreateChatCompletion(ctx context.Context, req ChatRequest) (string, error) {
	endpoint := strings.TrimRight(req.BaseURL, "/") + "/chat/completions"
	payload := map[string]any{
		"model":       req.Model,
		"messages":    req.Messages,
		"temperature": req.Temperature,
		"max_tokens":  req.MaxTokens,
	}
	if req.ResponseFormat != "" {
		payload["response_format"] = map[string]string{"type": req.ResponseFormat}
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return "", err
	}
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, bytes.NewReader(body))
	if err != nil {
		return "", err
	}
	httpReq.Header.Set("Content-Type", "application/json")
	if strings.TrimSpace(req.APIKey) != "" {
		httpReq.Header.Set("Authorization", "Bearer "+req.APIKey)
	}
	resp, err := c.httpClient.Do(httpReq)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	responseBody, err := readBoundedBody(resp.Body, maxLLMResponseBytes)
	if err != nil {
		return "", err
	}
	if resp.StatusCode < http.StatusOK || resp.StatusCode >= http.StatusMultipleChoices {
		return "", fmt.Errorf(
			"openai-compatible status %d: %s",
			resp.StatusCode,
			errorBodySnippet(responseBody, maxLLMErrorBodyBytes),
		)
	}
	var parsed struct {
		Choices []struct {
			Message struct {
				Content any `json:"content"`
			} `json:"message"`
		} `json:"choices"`
	}
	if err := json.Unmarshal(responseBody, &parsed); err != nil {
		return "", err
	}
	if len(parsed.Choices) == 0 {
		return "", fmt.Errorf("no choices returned")
	}
	return contentFromMessage(parsed.Choices[0].Message.Content)
}

func errorBodySnippet(body []byte, limit int) string {
	if limit > 0 && len(body) > limit {
		return strings.TrimSpace(
			strings.ToValidUTF8(string(body[:limit]), ""),
		) + "..."
	}
	return strings.TrimSpace(strings.ToValidUTF8(string(body), ""))
}

func contentFromMessage(raw any) (string, error) {
	switch typed := raw.(type) {
	case string:
		return typed, nil
	case []any:
		var builder strings.Builder
		for _, item := range typed {
			part, ok := item.(map[string]any)
			if !ok {
				continue
			}
			text, _ := part["text"].(string)
			builder.WriteString(text)
		}
		if builder.Len() == 0 {
			return "", fmt.Errorf("message content array had no text")
		}
		return builder.String(), nil
	default:
		return "", fmt.Errorf("unsupported message content type %T", raw)
	}
}
