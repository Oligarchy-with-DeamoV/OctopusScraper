package bootstrap

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"os"
	"time"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/app"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/config"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/exporter"
	notionexporter "github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/exporter/notion"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/fetcher"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/httpapi"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/observability"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/processor"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/storage"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/task"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/version"
	"github.com/joho/godotenv"
)

func Run(ctx context.Context, options Options) (err error) {
	runtimeCtx, cancelRuntime := context.WithCancel(ctx)
	defer cancelRuntime()
	if err := loadDotEnv(); err != nil {
		return err
	}
	serviceConfig, err := config.LoadServiceConfig()
	if err != nil {
		return fmt.Errorf("load service configuration: %w", err)
	}
	applyOptions(&serviceConfig, options)

	loggerRuntime, err := observability.NewLoggerRuntime(
		observability.LoggerOptions{
			Level:         serviceConfig.LogLevel,
			Format:        serviceConfig.LogFormat,
			FilePath:      serviceConfig.LogFile,
			RetentionDays: serviceConfig.LogRetentionDays,
		},
	)
	if err != nil {
		return err
	}
	defer func() {
		if closeErr := loggerRuntime.Close(); closeErr != nil {
			err = errors.Join(err, fmt.Errorf("close logger: %w", closeErr))
		}
	}()
	logger := loggerRuntime.Logger()
	metrics := observability.NewMetrics(version.Version)
	configManager := config.NewManager(serviceConfig.ScraperConfig, logger)
	configManager.SetHealthObserver(metrics.SetConfigHealth)
	configManager.SetRefreshObserver(metrics.RecordConfig)
	if _, err := configManager.LoadInitial(ctx); err != nil {
		return fmt.Errorf("load initial scraper configuration: %w", err)
	}

	fetcherFactory := fetcher.NewFactory(fetcher.FactoryOptions{
		RSSHubConnectTimeout: serviceConfig.RSSConnectTimeout,
		RSSHubReadTimeout:    serviceConfig.RSSReadTimeout,
		SummaryMaxLength:     serviceConfig.SummaryMaxLength,
	})
	processorFactory := processor.NewRegistry(
		processor.WithLogger(logger),
		processor.WithLLMOperationObserver(func(
			duration time.Duration,
			success bool,
		) {
			_ = metrics.RecordExternal("llm", duration, success)
		}),
	)
	configValidator := app.NewScraperConfigValidator(
		fetcherFactory,
		processorFactory,
	)
	if err := configValidator.Validate(configManager.CurrentScrapers()); err != nil {
		return fmt.Errorf("validate initial scraper configuration: %w", err)
	}

	canonicalStore, err := storage.NewPostgresStore(serviceConfig.Database, logger)
	if err != nil {
		return fmt.Errorf("create PostgreSQL store: %w", err)
	}
	if err := canonicalStore.Initialize(ctx); err != nil {
		canonicalStore.Close()
		return fmt.Errorf("initialize PostgreSQL store: %w", err)
	}

	executor := app.NewExecutor(
		logger,
		app.InstrumentedFetcherFactory{
			Factory: fetcherFactory,
			Metrics: metrics,
		},
		processorFactory,
		canonicalStore,
	)

	syncService, err := buildSyncService(
		serviceConfig,
		canonicalStore,
		metrics,
		logger,
	)
	if err != nil {
		canonicalStore.Close()
		return err
	}
	octopusRuntime := app.NewRuntime(
		logger,
		configManager,
		canonicalStore,
		syncService,
		serviceConfig.ScraperTimeout,
	)

	resultStore := openTaskResultStore(
		serviceConfig.TaskResultPath,
		logger,
	)
	taskManager, err := task.NewManager(
		logger,
		executor,
		serviceConfig.MaxConcurrentTasks,
		serviceConfig.MaxQueueSize,
		serviceConfig.ResultRetention,
		resultStore,
		metrics,
	)
	if err != nil {
		if resultStore != nil {
			_ = resultStore.Close()
		}
		canonicalStore.Close()
		return err
	}
	octopusRuntime.SetTaskManager(taskManager)

	if syncService != nil {
		syncService.Start(runtimeCtx)
	}

	configManager.SetOnConfigChanged(func(
		_ context.Context,
		scrapers []config.ScraperConfig,
	) error {
		if err := configValidator.Validate(scrapers); err != nil {
			return err
		}
		logger.Info(
			"Octopus scrapers reloaded",
			"scraper_count", len(scrapers),
		)
		return nil
	})
	watcherErrors := make(chan error, 1)
	go func() {
		watcherErrors <- configManager.Start(runtimeCtx, nil)
	}()

	api := httpapi.NewServer(
		logger,
		octopusRuntime,
		configManager,
		serviceConfig,
		metrics,
		version.Version,
	)
	api.SetLogLevelController(loggerRuntime)
	if serviceConfig.MCP.Enabled {
		api.EnableMCP(runtimeCtx, canonicalStore)
	}
	httpServer := &http.Server{
		Addr:              net.JoinHostPort(serviceConfig.Host, fmt.Sprint(serviceConfig.Port)),
		Handler:           api.Handler(),
		ReadHeaderTimeout: 10 * time.Second,
		IdleTimeout:       2 * time.Minute,
	}
	serverErrors := make(chan error, 1)
	go func() {
		logger.Info(
			"Starting OctopusScraper service",
			"host", serviceConfig.Host,
			"port", serviceConfig.Port,
			"debug", serviceConfig.Debug,
			"log_level", serviceConfig.LogLevel,
			"log_format", serviceConfig.LogFormat,
			"log_file_enabled", serviceConfig.LogFile != "",
			"scraper_config_dir", serviceConfig.ScraperConfig.Directory,
			"version", version.Version,
			"commit", version.Commit,
		)
		serverErrors <- httpServer.ListenAndServe()
	}()

	var runErr error
	select {
	case <-runtimeCtx.Done():
	case err := <-serverErrors:
		if !errors.Is(err, http.ErrServerClosed) {
			runErr = fmt.Errorf("serve HTTP: %w", err)
		}
	case err := <-watcherErrors:
		if err != nil && !errors.Is(err, context.Canceled) {
			runErr = fmt.Errorf("watch scraper configuration: %w", err)
		}
	}
	cancelRuntime()

	httpShutdownCtx, cancelHTTPShutdown := context.WithTimeout(
		context.Background(),
		30*time.Second,
	)
	if err := httpServer.Shutdown(httpShutdownCtx); err != nil {
		if runErr == nil {
			runErr = fmt.Errorf("shutdown HTTP server: %w", err)
		}
		_ = httpServer.Close()
	}
	cancelHTTPShutdown()
	runtimeShutdownCtx, cancelRuntimeShutdown := context.WithTimeout(
		context.Background(),
		30*time.Second,
	)
	if err := octopusRuntime.Stop(runtimeShutdownCtx); err != nil &&
		runErr == nil {
		runErr = fmt.Errorf("stop runtime: %w", err)
	}
	cancelRuntimeShutdown()
	return runErr
}

func buildSyncService(
	serviceConfig config.ServiceConfig,
	store storage.CanonicalStore,
	metrics *observability.Metrics,
	logger *slog.Logger,
) (app.SyncService, error) {
	if !serviceConfig.Notion.Enabled {
		if store != nil {
			if err := store.RegisterTarget(context.Background(), "notion", false); err != nil {
				return nil, fmt.Errorf("disable Notion exporter target: %w", err)
			}
		}
		return nil, nil
	}
	client, err := notionexporter.NewClient(
		serviceConfig.Notion,
		&http.Client{Timeout: maxDuration(serviceConfig.UploadTimeout, 30*time.Second)},
	)
	if err != nil {
		return nil, fmt.Errorf("create Notion client: %w", err)
	}
	if err := store.RegisterTarget(context.Background(), client.ID(), true); err != nil {
		return nil, fmt.Errorf("register Notion exporter target: %w", err)
	}
	service, err := exporter.NewManager(exporter.Options{
		BatchSize:   serviceConfig.Notion.BatchSize,
		Interval:    serviceConfig.Notion.Interval,
		Lease:       serviceConfig.Notion.Lease,
		MaxAttempts: serviceConfig.Notion.MaxAttempts,
	}, store, client)
	if err != nil {
		return nil, fmt.Errorf("create exporter manager: %w", err)
	}
	return &app.InstrumentedSyncService{
		Service:  service,
		Metrics:  metrics,
		Interval: serviceConfig.Notion.Interval,
		Logger:   logger,
	}, nil
}

func openTaskResultStore(
	path string,
	logger *slog.Logger,
) *task.ResultStore {
	store, err := task.NewResultStore(path)
	if err == nil {
		return store
	}
	logger.Error(
		"Task result persistence unavailable; continuing without history",
		"path",
		path,
		"error",
		err,
	)
	return nil
}

func loadDotEnv() error {
	err := godotenv.Load()
	if err == nil || errors.Is(err, os.ErrNotExist) {
		return nil
	}
	return fmt.Errorf("load .env: %w", err)
}

func applyOptions(serviceConfig *config.ServiceConfig, options Options) {
	if options.Host != "" {
		serviceConfig.Host = options.Host
	}
	if options.Port != 0 {
		serviceConfig.Port = options.Port
	}
	if options.Debug {
		serviceConfig.Debug = true
	}
	if options.LogLevel != "" {
		serviceConfig.LogLevel = options.LogLevel
	}
	if options.LogFormat != "" {
		serviceConfig.LogFormat = "json"
	}
	if options.ScraperConfigDir != "" {
		serviceConfig.ScraperConfig.Directory = options.ScraperConfigDir
	}
}

func maxDuration(left, right time.Duration) time.Duration {
	if left > right {
		return left
	}
	return right
}
