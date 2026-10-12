import { DIVISIONS, MAX_FLOORS, MANAGERS } from '../domain/company.js';

const materialColor = value => Number.parseInt(value.slice(1), 16);

export const DIVS = DIVISIONS.map(division => ({
  ...division,
  name: `Divisi ${division.name}`,
  accent: division.colors.accent,
  floor: materialColor(division.colors.floor),
  wall: materialColor(division.colors.wall),
  screen: materialColor(division.colors.screen),
  accentColor: materialColor(division.colors.accent),
}));

export { MAX_FLOORS, MANAGERS };

// These services live in separate one-story pavilions on level zero.
export const KANTIN = 0;
export const OWNER = 0;
export const RAPAT = 0;
