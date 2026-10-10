// state shared (and reassigned) by several modules
export const DEMO = {
  jobs: { remoteok: { FILTERED_OUT: 95, CANDIDATE: 4 }, remotive: { FILTERED_OUT: 20, CANDIDATE: 6 }, greenhouse: { FILTERED_OUT: 210, CANDIDATE: 15 }, lever: { FILTERED_OUT: 30, CANDIDATE: 3 }, kalibrr: { FILTERED_OUT: 40, CANDIDATE: 2 }, dealls: { FILTERED_OUT: 18, CANDIDATE: 1 } },
  applications: { SUBMITTED: 3, VIEWED: 1, INTERVIEW: 1, PENDING_APPROVAL: 2 },
  leads: { freelancer: { NEW: 420, INTERESTED: 12 }, 'projects.co.id': { NEW: 9 } }, llm: { success: 9, error: 1 }, forms: { filled: 4, captcha: 1 }, history: 14,
};

export const store = {
  S: DEMO, // latest stats.json (or DEMO when the server is not running)
  live: false,
  desk: { ratings: {}, instructions: {}, undelivered: [], tray: 0 },
  overview: false, // camera shows the whole building
  fp: false, yaw: 0, pitch: 0, // owner POV camera
};
