package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/bootstrap"
)

func main() {
	arguments := os.Args[1:]
	if err := run(arguments); err != nil {
		writeFatalError(os.Stderr, arguments, err)
		os.Exit(1)
	}
}

func writeFatalError(
	writer io.Writer,
	arguments []string,
	err error,
) {
	timestamp := time.Now().UTC().Format(time.RFC3339)
	if fatalLogFormat(arguments) == "json" {
		_ = json.NewEncoder(writer).Encode(struct {
			Time  string `json:"time"`
			Level string `json:"level"`
			Event string `json:"event"`
			Error string `json:"error"`
		}{
			Time:  timestamp,
			Level: "error",
			Event: "OctopusScraper command failed",
			Error: err.Error(),
		})
		return
	}
	fmt.Fprintf(
		writer,
		"%s [error] OctopusScraper command failed error=%q\n",
		timestamp,
		err,
	)
}

func fatalLogFormat(arguments []string) string {
	for index, argument := range arguments {
		if argument == "--log-format" && index+1 < len(arguments) {
			return strings.ToLower(strings.TrimSpace(arguments[index+1]))
		}
		if value, found := strings.CutPrefix(
			argument,
			"--log-format=",
		); found {
			return strings.ToLower(strings.TrimSpace(value))
		}
	}
	format := os.Getenv("LOG_FORMAT")
	if format == "" {
		format = os.Getenv("OCTOPUS_LOG_FORMAT")
	}
	return strings.ToLower(strings.TrimSpace(format))
}

func run(arguments []string) error {
	if len(arguments) > 0 && arguments[0] == "help" {
		writeRootUsage(os.Stdout)
		return nil
	}
	if len(arguments) > 0 && arguments[0] == "healthcheck" {
		if containsHelpFlag(arguments[1:]) {
			writeHealthcheckUsage(os.Stdout)
			return nil
		}
		return runHealthcheck(arguments[1:])
	}
	if len(arguments) > 0 && arguments[0] == "serve" {
		arguments = arguments[1:]
	}
	if containsHelpFlag(arguments) {
		writeServeUsage(os.Stdout)
		return nil
	}
	options, err := parseServeOptions(arguments)
	if err != nil {
		return err
	}
	ctx, stop := signal.NotifyContext(
		context.Background(),
		os.Interrupt,
		syscall.SIGTERM,
	)
	defer stop()
	return bootstrap.Run(ctx, options)
}

func parseServeOptions(arguments []string) (bootstrap.Options, error) {
	flags := flag.NewFlagSet("octopus_service", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	options := bootstrap.Options{}
	flags.StringVar(
		&options.Host,
		"host",
		"",
		"Host to bind the service",
	)
	flags.IntVar(
		&options.Port,
		"port",
		0,
		"Port to bind the service",
	)
	flags.BoolVar(
		&options.Debug,
		"debug",
		false,
		"Enable debug mode",
	)
	flags.StringVar(
		&options.LogLevel,
		"log-level",
		"",
		"Log level",
	)
	flags.StringVar(
		&options.LogFormat,
		"log-format",
		"",
		"Log format: plain or json",
	)
	flags.StringVar(
		&options.ScraperConfigDir,
		"scraper-config-dir",
		"",
		"Directory containing scraper YAML files",
	)
	if err := flags.Parse(arguments); err != nil {
		return bootstrap.Options{}, err
	}
	if flags.NArg() != 0 {
		return bootstrap.Options{}, fmt.Errorf(
			"unexpected serve arguments: %v",
			flags.Args(),
		)
	}
	portProvided := false
	flags.Visit(func(current *flag.Flag) {
		if current.Name == "port" {
			portProvided = true
		}
	})
	if portProvided && (options.Port < 1 || options.Port > 65535) {
		return bootstrap.Options{}, errors.New("port must be between 1 and 65535")
	}
	if options.LogFormat != "" &&
		options.LogFormat != "plain" &&
		options.LogFormat != "json" {
		return bootstrap.Options{}, errors.New("log format must be plain or json")
	}
	return options, nil
}

func runHealthcheck(arguments []string) error {
	flags := flag.NewFlagSet("healthcheck", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	port := os.Getenv("SERVICE_PORT")
	if port == "" {
		port = os.Getenv("OCTOPUS_PORT")
	}
	if port == "" {
		port = "8000"
	}
	url := flags.String(
		"url",
		"http://localhost:"+port+"/health/liveness",
		"Health endpoint URL",
	)
	timeout := flags.Duration("timeout", 5*time.Second, "Request timeout")
	if err := flags.Parse(arguments); err != nil {
		return err
	}
	if flags.NArg() != 0 {
		return fmt.Errorf("unexpected healthcheck arguments: %v", flags.Args())
	}
	if *timeout <= 0 {
		return errors.New("healthcheck timeout must be positive")
	}
	client := &http.Client{Timeout: *timeout}
	response, err := client.Get(*url)
	if err != nil {
		return fmt.Errorf("healthcheck request failed: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return fmt.Errorf("healthcheck returned %s", response.Status)
	}
	return nil
}

func containsHelpFlag(arguments []string) bool {
	for _, argument := range arguments {
		if argument == "-h" || argument == "--help" {
			return true
		}
	}
	return false
}

func writeRootUsage(writer io.Writer) {
	fmt.Fprintln(writer, `Usage:
  octopus_service [serve] [flags]
  octopus_service healthcheck [flags]
  octopus_service help`)
}

func writeServeUsage(writer io.Writer) {
	fmt.Fprintln(writer, `Usage: octopus_service [serve] [flags]

Flags:
  --host string                 Host to bind the service
  --port int                    Port to bind the service
  --debug                       Enable debug mode
  --log-level string            Log level
  --log-format plain|json       Log format
  --scraper-config-dir string   Directory containing scraper YAML files`)
}

func writeHealthcheckUsage(writer io.Writer) {
	fmt.Fprintln(writer, `Usage: octopus_service healthcheck [flags]

Flags:
  --url string        Health endpoint URL
  --timeout duration  Request timeout (default 5s)`)
}
