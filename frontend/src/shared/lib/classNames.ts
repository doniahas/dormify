/**
 * Joins class names, skipping falsy entries - the one helper every CSS
 * Module consumer needs for conditional classes:
 *   className={cx(styles.statTab, styles[color], isActive && styles.active)}
 */
export type ClassValue = string | false | null | undefined;

export function cx(...values: ClassValue[]): string {
  return values.filter(Boolean).join(' ');
}
