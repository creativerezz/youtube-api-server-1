# MCP Server Configuration Guide

## Overview

This document describes the enhanced MCP server configuration format used in `cline_mcp_settings.json`. The configuration has been redesigned for production readiness with comprehensive error handling, performance optimizations, and security features.

## Schema Version

Current schema: `https://mcp-spec.org/schema/mcp-config-v1.0.json`

## Configuration Structure

### Root Level

```json
{
  "$schema": "...",
  "version": "1.0",
  "metadata": {...},
  "global": {...},
  "mcpServers": {...},
  "fallback": {...}
}
```

### Metadata Section

Contains configuration metadata and environment information:

- `description`: Human-readable description
- `lastUpdated`: ISO 8601 timestamp of last modification
- `environment`: Current environment (${ENVIRONMENT:development})
- `schemaVersion`: Configuration schema version

### Global Configuration

#### Connection Settings
- `timeout`: Default connection timeout in milliseconds (30000)
- `retry`: Retry policy configuration
  - `maxAttempts`: Maximum retry attempts (3)
  - `backoff`: Backoff strategy ("exponential")
  - `jitter`: Add randomness to retry delays (true)
- `pool`: Connection pooling settings
  - `maxConnections`: Maximum concurrent connections (10)
  - `idleTimeout`: Connection idle timeout in milliseconds (60000)

#### Security Settings
- `validateCertificates`: Enable SSL certificate validation (true)
- `allowedHosts`: Whitelist of allowed hostnames
- `apiKey`: Global API key from environment variable

#### Performance Settings
- `enableCaching`: Enable response caching (true)
- `cacheTtl`: Cache time-to-live in milliseconds (3600000)
- `rateLimit`: Rate limiting configuration
  - `requests`: Maximum requests per window (100)
  - `windowMs`: Rate limit window in milliseconds (60000)

#### Monitoring Settings
- `enableHealthChecks`: Enable automatic health monitoring (true)
- `healthCheckInterval`: Health check frequency in milliseconds (30000)
- `metrics`: Prometheus metrics configuration

### MCP Servers Section

Each server configuration includes:

#### Basic Configuration
- `url`: Server endpoint URL (supports environment variables)
- `auth`: Authentication configuration
  - `type`: Authentication method ("bearer", "api-key", "basic")
  - `token`: Authentication token from environment variable

#### Capabilities
Array of supported MCP capabilities:
- `context.search`
- `context.retrieve`
- `context.suggest`
- `tools.execute`
- `resources.read`

#### Server-Specific Config
- `maxResults`: Maximum results per request
- `timeout`: Server-specific timeout override
- `fallback`: Fallback server configuration

#### Health Monitoring
- `endpoint`: Health check endpoint
- `interval`: Health check frequency
- `timeout`: Health check timeout

### Fallback Servers

Backup servers that can be used when primary servers fail:

```json
"fallback": {
  "ServerName": {
    "url": "backup-url",
    "auth": {...},
    "capabilities": [...]
  }
}
```

## Environment Variables

The configuration supports environment variable substitution using `${VAR_NAME:default}` syntax:

| Variable | Description | Default |
|----------|-------------|---------|
| `ENVIRONMENT` | Deployment environment | `development` |
| `MCP_API_KEY` | Global API key | (required) |
| `CONTEXT7_URL` | Context7 server URL | `https://mcp.context7.com/mcp` |
| `CONTEXT7_TOKEN` | Context7 authentication token | (required) |
| `CONTEXT7_BACKUP_TOKEN` | Backup server token | (required) |

## Error Handling

### Connection Failures
- Automatic retry with exponential backoff
- Circuit breaker pattern implementation
- Fallback server activation

### Validation Errors
- JSON schema validation on startup
- Environment variable validation
- URL format validation

### Runtime Errors
- Connection timeout handling
- Health check failures trigger fallback
- Graceful degradation to cached responses

## Performance Optimizations

### Connection Pooling
- Reuses connections to reduce overhead
- Configurable pool size and idle timeouts

### Caching
- Response caching with TTL
- Cache invalidation on server changes

### Rate Limiting
- Prevents server overload
- Configurable per-server limits

## Security Features

### Authentication
- Multiple authentication methods supported
- Token rotation capabilities
- Environment variable isolation

### Network Security
- SSL certificate validation
- Host whitelisting
- Secure defaults (no plain HTTP)

### Access Control
- Capability-based permissions
- Server-specific authentication
- Audit logging support

## Migration Guide

To migrate from the old configuration format:

1. Replace the simple server object with the enhanced structure
2. Add environment variables for sensitive data
3. Configure global settings as needed
4. Add health check endpoints
5. Test in development environment first

### Before
```json
{
  "mcpServers": {
    "Context7": {
      "serverUrl": "https://mcp.context7.com/mcp"
    }
  }
}
```

### After
```json
{
  "$schema": "...",
  "version": "1.0",
  "metadata": {...},
  "global": {...},
  "mcpServers": {
    "Context7": {
      "url": "${CONTEXT7_URL}",
      "auth": {...},
      "capabilities": [...],
      "config": {...},
      "health": {...}
    }
  }
}
```

## Best Practices

1. **Environment Variables**: Use environment variables for all sensitive data
2. **Health Checks**: Always configure health check endpoints
3. **Fallbacks**: Define fallback servers for critical services
4. **Monitoring**: Enable metrics collection for observability
5. **Validation**: Test configuration validation before deployment
6. **Documentation**: Keep server capabilities and requirements updated

## Troubleshooting

### Common Issues

1. **Connection Timeouts**: Check network connectivity and firewall rules
2. **Authentication Failures**: Verify environment variables are set correctly
3. **Schema Validation Errors**: Ensure all required fields are present
4. **Health Check Failures**: Confirm server endpoints are accessible

### Debug Mode

Set `ENVIRONMENT=debug` to enable additional logging and disable some security restrictions for troubleshooting.

## Support

For issues with MCP server configurations, check:
1. Server documentation
2. Network connectivity
3. Authentication credentials
4. Configuration schema compliance