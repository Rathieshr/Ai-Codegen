const HOURS_PER_DAY = 8;
const HOUR_PRECISION = 4;

export function formatEngineeringEffort(engineeringDays: number): string {
  const rawHours = Math.max(0, Number(engineeringDays) || 0) * HOURS_PER_DAY;
  const totalHours = Math.round(rawHours * HOUR_PRECISION) / HOUR_PRECISION;

  if (totalHours <= HOURS_PER_DAY) return formatHours(totalHours);

  const days = Math.floor(totalHours / HOURS_PER_DAY);
  const remainingHours = Math.round((totalHours - days * HOURS_PER_DAY) * HOUR_PRECISION) / HOUR_PRECISION;
  const dayLabel = `${days} ${days === 1 ? 'day' : 'days'}`;
  return remainingHours ? `${dayLabel} ${formatHours(remainingHours)}` : dayLabel;
}

function formatHours(hours: number): string {
  const value = Number.isInteger(hours) ? String(hours) : String(Number(hours.toFixed(2)));
  return `${value} ${hours === 1 ? 'hour' : 'hours'}`;
}
