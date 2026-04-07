import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const BACKEND_URL = process.env.TSUNAMI_BACKEND_URL || "http://localhost:8001";

async function apiCall(method: string, path: string, body?: unknown): Promise<unknown> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 10000)
  try {
    const res = await fetch(`${BACKEND_URL}/api${path}`, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    })
    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText)
      throw new Error(`API ${res.status}: ${text}`)
    }
    if (res.status === 204) return { ok: true }
    return res.json()
  } finally {
    clearTimeout(timeout)
  }
}

const server = new McpServer({
  name: "tsunami",
  version: "0.1.0",
});

// Tool 1: Health check
server.tool("tsunami_health", "Check if the tsunami simulator backend is running", {}, async () => {
  try {
    const result = await apiCall("GET", "/health");
    return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    return { content: [{ type: "text", text: `Backend unreachable: ${msg}` }], isError: true };
  }
});

// Tool 2: List simulations
server.tool("tsunami_list_simulations", "List all tsunami simulations with their status", {}, async () => {
  try {
    const result = await apiCall("GET", "/simulations");
    return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    return { content: [{ type: "text", text: `Error: ${msg}` }], isError: true };
  }
});

// Tool 3: Get simulation
server.tool("tsunami_get_simulation", "Get details for a specific simulation", {
  uid: z.string().describe("Simulation UID"),
}, async ({ uid }) => {
  try {
    const result = await apiCall("GET", `/simulations/${uid}`);
    return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    return { content: [{ type: "text", text: `Error: ${msg}` }], isError: true };
  }
});

// Tool 4: Create simulation
server.tool("tsunami_create_simulation", "Create a new tsunami simulation. After creating, use tsunami_run_coarse to execute it.", {
  name: z.string().describe("Simulation name"),
  earthquake_lat: z.number().describe("Epicenter latitude (-90 to 90)"),
  earthquake_lon: z.number().describe("Epicenter longitude (-180 to 180)"),
  earthquake_magnitude: z.number().describe("Magnitude (5.0 to 10.0)"),
  earthquake_direction: z.number().describe("Direction in degrees (0-359)"),
  earthquake_depth_km: z.number().optional().describe("Depth in km (default 15)"),
  grid_resolution_km: z.number().optional().describe("Grid resolution in km (default 2.0, use 20-50 for fast runs)"),
  duration_hours: z.number().optional().describe("Simulation duration in hours (default 6.0)"),
  earthquake_datetime: z.string().optional().describe("UTC datetime for tidal offset (ISO 8601, e.g. 2026-03-11T05:46:00Z)"),
}, async (params) => {
  try {
    const result = await apiCall("POST", "/simulations", params);
    return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    return { content: [{ type: "text", text: `Error: ${msg}` }], isError: true };
  }
});

// Tool 5: Run coarse simulation
server.tool("tsunami_run_coarse", "Run the coarse SWE simulation. This also auto-detects coastal impact zones and runs detail Boussinesq simulations. Use tsunami_get_results or tsunami_get_detail_results to see outcomes.", {
  uid: z.string().describe("Simulation UID"),
}, async ({ uid }) => {
  try {
    const result = await apiCall("POST", `/simulations/${uid}/run-coarse`);
    return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    return { content: [{ type: "text", text: `Error: ${msg}` }], isError: true };
  }
});

// Tool 6: Get results
server.tool("tsunami_get_results", "Get coarse simulation results including coastal impacts, suggested zones, and max wave height.", {
  uid: z.string().describe("Simulation UID"),
}, async ({ uid }) => {
  try {
    const result = await apiCall("GET", `/simulations/${uid}/coarse-result`);
    return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    return { content: [{ type: "text", text: `Error: ${msg}` }], isError: true };
  }
});

// Tool 7: List presets
server.tool("tsunami_list_presets", "List available preset earthquake locations", {}, async () => {
  try {
    const result = await apiCall("GET", "/presets/locations");
    return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    return { content: [{ type: "text", text: `Error: ${msg}` }], isError: true };
  }
});

// Tool 8: Delete simulation
server.tool("tsunami_delete_simulation", "Delete a simulation and all its results", {
  uid: z.string().describe("Simulation UID"),
}, async ({ uid }) => {
  try {
    const result = await apiCall("DELETE", `/simulations/${uid}`);
    return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    return { content: [{ type: "text", text: `Error: ${msg}` }], isError: true };
  }
});

// Tool 9: Get detail results
server.tool("tsunami_get_detail_results", "Get detail zone results (inundation, runup) from automatic coastal refinement. Run after run-coarse completes.", {
  uid: z.string().describe("Simulation UID"),
}, async ({ uid }) => {
  try {
    const result = await apiCall("GET", `/simulations/${uid}/detail-results`);
    return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    return { content: [{ type: "text", text: `Error: ${msg}` }], isError: true };
  }
});

// Tool 10: Compute tides
server.tool("tsunami_compute_tides", "Compute global tidal animation. Returns frame count and grid info.", {
  start_datetime: z.string().describe("UTC datetime (ISO 8601)"),
  duration_hours: z.number().optional(),
  resolution_km: z.number().optional(),
}, async (params) => {
  try {
    const result = await apiCall("POST", "/tides/compute", params) as any;
    const summary = {
      frame_count: result.frames?.length ?? 0,
      grid_size: `${result.frame_rows}x${result.frame_cols}`,
      grid_bounds: result.grid_bounds,
      message: "Tidal frames computed. View animation at http://localhost:3000 (click 'Show Global Tides').",
    };
    return { content: [{ type: "text", text: JSON.stringify(summary, null, 2) }] };
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    return { content: [{ type: "text", text: `Error: ${msg}` }], isError: true };
  }
});

// Tool 11: Check bathymetry
server.tool("tsunami_check_bathymetry", "Check which bathymetry data sources are available for a given region", {
  lat_min: z.number(),
  lat_max: z.number(),
  lon_min: z.number(),
  lon_max: z.number(),
}, async ({ lat_min, lat_max, lon_min, lon_max }) => {
  try {
    const result = await apiCall("GET", `/bathymetry/check?lat_min=${lat_min}&lat_max=${lat_max}&lon_min=${lon_min}&lon_max=${lon_max}`);
    return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    return { content: [{ type: "text", text: `Error: ${msg}` }], isError: true };
  }
});

// Tool 12: List focus zones
server.tool("tsunami_list_focus_zones", "List focus zones for a simulation (auto-created after coarse run)", {
  uid: z.string().describe("Simulation UID"),
}, async ({ uid }) => {
  try {
    const result = await apiCall("GET", `/simulations/${uid}/focus-zones`);
    return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    return { content: [{ type: "text", text: `Error: ${msg}` }], isError: true };
  }
});

// Tool 13: Export
server.tool("tsunami_export", "Get export URL for simulation results", {
  uid: z.string().describe("Simulation UID"),
  format: z.enum(["geojson"]).optional(),
}, async ({ uid, format }) => {
  try {
    return { content: [{ type: "text", text: `Export URL: ${BACKEND_URL}/api/simulations/${uid}/export?format=${format || "geojson"}` }] };
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    return { content: [{ type: "text", text: `Error: ${msg}` }], isError: true };
  }
});

// Start
const transport = new StdioServerTransport();
await server.connect(transport);
