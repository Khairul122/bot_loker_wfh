function responseData(response) {
  return response.json().catch(() => ({}));
}

export function createOfficeApi(fetchImpl = globalThis.fetch, baseUrl = '') {
  if (typeof fetchImpl !== 'function') throw new TypeError('A fetch implementation is required.');

  async function request(path, options) {
    try {
      const response = await fetchImpl(`${baseUrl}${path}`, options);
      return {
        ok: response.ok,
        status: response.status,
        data: await responseData(response),
      };
    } catch {
      return { ok: false, status: 0, data: {} };
    }
  }

  return Object.freeze({
    get: (path, options = {}) => request(path, { ...options, cache: 'no-store' }),
    post: (path, body, options = {}) => request(path, {
      ...options,
      method: 'POST',
      headers: body ? { 'Content-Type': 'application/json' } : {},
      body: body ? JSON.stringify(body) : undefined,
    }),
  });
}

const officeApi = createOfficeApi();
export const { get, post } = officeApi;
