import company from '../../company.json' with { type: 'json' };

const managers = Object.fromEntries(company.divisions.map(({ id, manager }) => [id, manager]));

if (company.max_floors > 7 || company.divisions.length > company.max_floors) {
  throw new Error('Office divisions exceed the seven-floor building limit.');
}

export const MAX_FLOORS = company.max_floors;
export const MANAGERS = Object.freeze(managers);
export const DIVISIONS = Object.freeze(company.divisions.map(division => Object.freeze({ ...division })));
export const EMPLOYEES = Object.freeze(company.employees.map(employee => Object.freeze({
  ...employee,
  role: employee.title,
  isManager: MANAGERS[employee.division] === employee.id,
})));

export function employeeById(id) {
  return EMPLOYEES.find(employee => employee.id === id) ?? null;
}
