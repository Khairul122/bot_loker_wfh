// every employee, in desk order (the order also picks their house and KPI row)
import tegar from './tegar.js';
import reno from './reno.js';
import rima from './rima.js';
import gery from './gery.js';
import leva from './leva.js';
import kalia from './kalia.js';
import dela from './dela.js';
import sari from './sari.js';
import eli from './eli.js';
import cora from './cora.js';
import lulu from './lulu.js';
import faris from './faris.js';
import subi from './subi.js';
import tara from './tara.js';
import ivan from './ivan.js';
import lido from './lido.js';
import nara from './nara.js';
import tama from './tama.js';
import bimo from './bimo.js';
import mira from './mira.js';
import { EMPLOYEES } from '../../domain/company.js';

const VISUAL_BY_ID = new Map([
  ['tegar', tegar], ['reno', reno], ['rima', rima], ['gery', gery], ['leva', leva],
  ['kalia', kalia], ['dela', dela], ['sari', sari], ['eli', eli], ['cora', cora],
  ['lulu', lulu], ['faris', faris], ['subi', subi], ['tara', tara], ['ivan', ivan],
  ['lido', lido], ['nara', nara], ['tama', tama], ['bimo', bimo], ['mira', mira],
]);

export const STAFF = EMPLOYEES.map(employee => {
  const visual = VISUAL_BY_ID.get(employee.id);
  if (!visual) throw new Error(`Missing visual definition for employee ${employee.id}`);

  return {
    ...visual,
    ...employee,
    role: employee.title,
    div: employee.division,
  };
});
