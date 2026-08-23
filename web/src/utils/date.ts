/** 本地时区日期工具（toISOString 是 UTC，晚间调用会差一天）。 */

export function localISO(d: Date = new Date()): string {
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/** 基于 yyyy-mm-dd 加减天数，返回同格式字符串。 */
export function addDays(base: string, n: number): string {
  const d = new Date(`${base}T00:00:00`);
  d.setDate(d.getDate() + n);
  return localISO(d);
}

/** '2026-08-24' → '8/24'（紧凑展示）。 */
export function fmtMD(iso: string): string {
  return `${Number(iso.slice(5, 7))}/${Number(iso.slice(8, 10))}`;
}
