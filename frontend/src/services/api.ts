/**
 * API client and diagnostic models for AI Data Intelligence Cloud
 */

export interface HealthServices {
  api: string;
  metadata_store: string;
  background_worker: string;
  [key: string]: string;
}

export interface HealthResponse {
  status: string;
  app_name: string;
  version: string;
  environment: string;
  timestamp: string;
  services: HealthServices;
}

export interface HealthCheckResult {
  data: HealthResponse | null;
  latencyMs: number;
  error: string | null;
  checkedAt: string;
}

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

/**
 * Fetch backend health status and measure round-trip latency.
 */
export async function checkBackendHealth(): Promise<HealthCheckResult> {
  const startTime = performance.now();
  const timestamp = new Date().toISOString();

  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/health`, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
      },
    });

    const latencyMs = Math.round(performance.now() - startTime);

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const data: HealthResponse = await response.json();
    return {
      data,
      latencyMs,
      error: null,
      checkedAt: timestamp,
    };
  } catch (err: unknown) {
    const latencyMs = Math.round(performance.now() - startTime);
    const errorMessage = err instanceof Error ? err.message : 'Unknown network failure';
    return {
      data: null,
      latencyMs,
      error: errorMessage,
      checkedAt: timestamp,
    };
  }
}
