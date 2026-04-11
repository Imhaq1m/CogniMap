/**
 * Shared API Client — All fetch calls to the Flask backend.
 */

const API = {
  async get(url) {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`GET ${url} failed: ${resp.status}`);
    return resp.json();
  },

  async post(url, body) {
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ error: resp.statusText }));
      throw new Error(err.error || `POST ${url} failed: ${resp.status}`);
    }
    return resp.json();
  },

  async delete(url) {
    const resp = await fetch(url, { method: "DELETE" });
    if (!resp.ok) throw new Error(`DELETE ${url} failed: ${resp.status}`);
    return resp.json();
  },
};
