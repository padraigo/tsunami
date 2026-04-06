import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const BACKEND_URL = process.env.TSUNAMI_BACKEND_URL || "http://localhost:8001";

async function apiCall(method: string, path: string, body?: unknown): Promise<unknown> {
  const res = await fetch(`${BACKEND_URL}/api${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${text}`);
  }
  if (res.status === 204) return { ok: true };
  return res.json();
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
    const message = e instanceof Error ? e.message : String(e);
    return { content: [{ type: "text", text: `Backend unreachable: ${message}` }], isError: true };
  }
});

// Tool 2: List simulations
server.tool("tsunami_list_simulations", "List all tsunami simulations with their status", {}, async () => {
  const result = await apiCall("GET", "/simulations");
  return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
});

// Tool 3: Get simulation
server.tool("tsunami_get_simulation", "Get details for a specific simulation", {
  uid: z.string().describe("Simulation UID"),
}, async ({ uid }) => {
  const result = await apiCall("GET", `/simulations/${uid}`);
  return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
});

// Tool 4: Create simulation
server.tool("tsunami_create_simulation", "Create a new tsunami simulation", {
  name: z.string().describe("Simulation name"),
  earthquake_lat: z.number().describe("Epicenter latitude (-90 to 90)"),
  earthquake_lon: z.number().describe("Epicenter longitude (-180 to 180)"),
  earthquake_magnitude: z.number().describe("Magnitude (5.0 to 10.0)"),
  earthquake_direction: z.number().describe("Direction in degrees (0-359)"),
  earthquake_depth_km: z.number().optional().describe("Depth in km (default 15)"),
}, async (params) => {
  const result = await apiCall("POST", "/simulations", params);
  return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
});

// Tool 5: Run coarse simulation
server.tool("tsunami_run_coarse", "Run the coarse SWE simulation for a given simulation", {
  uid: z.string().describe("Simulation UID"),
}, async ({ uid }) => {
  const result = await apiCall("POST", `/simulations/${uid}/run-coarse`);
  return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
});

// Tool 6: Get results
server.tool("tsunami_get_results", "Get coarse simulation results (impacts, wave heights, zones)", {
  uid: z.string().describe("Simulation UID"),
}, async ({ uid }) => {
  const result = await apiCall("GET", `/simulations/${uid}/coarse-result`);
  return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
});

// Tool 7: List presets
server.tool("tsunami_list_presets", "List available preset earthquake locations", {}, async () => {
  const result = await apiCall("GET", "/presets/locations");
  return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
});

// Start
const transport = new StdioServerTransport();
await server.connect(transport);
